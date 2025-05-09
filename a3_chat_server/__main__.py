import logging
import select
import socket
import threading
from argparse import ArgumentParser, Namespace

running = True
max_users = 16
clients = {}  # username -> socket
client_sockets = {}  # socket -> (username, authenticated)
server_socket = None


logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def parse_arguments() -> Namespace:
    """
    Parse command line arguments for the chat server.
    The two valid options are:
        --address: The host to listen at. Default is "0.0.0.0"
        --port: The port to listen at. Default is 5378
    :return: The parsed arguments in a Namespace object.
    """

    parser: ArgumentParser = ArgumentParser(
        prog="python -m a3_chat_server",
        description="A3 Chat Server assignment for the VU Computer Networks course.",
        epilog="Authors: Your group name"
    )
    parser.add_argument("-a", "--address",
                        type=str, help="Set server address", default="0.0.0.0")
    parser.add_argument("-p", "--port",
                        type=int, help="Set server port", default=5378)
    return parser.parse_args()


def disconnect_client(client_socket: socket.socket) -> None:

    global client_sockets
    global clients

    try:
        username, _ = client_sockets.get(client_socket, (None, False))
        if username:
            del clients[username]
            logger.info(f"User {username} disconnected")

        if client_socket in client_sockets:
            del client_sockets[client_socket]

        client_socket.close()
    except Exception as e:
        logger.error(f"Error disconnecting client: {e}")


def send_message(client_socket: socket.socket, message: str) -> None:

    try:
        message_bytes = message.encode('utf-8')
        bytes_len = len(message_bytes)
        bytes_sent = 0

        while bytes_sent < bytes_len:
            bytes_sent += client_socket.send(message_bytes[bytes_sent:])

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        disconnect_client(client_socket)


def send_error(client_socket: socket.socket, error_message: str) -> None:
    send_message(client_socket, error_message)


def handle_hello_from(client_socket: socket.socket, parts: list, authenticated: bool) -> None:

    global clients
    global max_users
    global client_sockets

    if authenticated:
        send_error(client_socket, "BAD-RQST-HDR\n")
        return

    if len(parts) != 2:
        send_error(client_socket, "BAD-RQST-BODY\n")
        return

    username = parts[1].strip()

    # Check for illegal characters
    illegal_chars = '!@#$%^&*, '
    if any(char in illegal_chars for char in username):
        send_error(client_socket, "BAD-RQST-BODY\n")
        return

    # Check if username is already in use
    if username in clients:
        send_error(client_socket, "IN-USE\n")
        return

    # Check if server is full
    if len(clients) >= max_users:
        send_error(client_socket, "BUSY\n")
        return

    # Successfully authenticate user
    clients[username] = client_socket
    client_sockets[client_socket] = (username, True)
    send_message(client_socket, f"HELLO {username}\n")
    logger.info(f"User {username} authenticated")


def handle_list(client_socket: socket.socket, authenticated: bool) -> None:

    global clients

    if not authenticated:
        send_error(client_socket, "BAD-RQST-HDR\n")
        return

    user_list = ",".join(clients.keys())
    send_message(client_socket, f"LIST-OK {user_list}\n")


def handle_send(client_socket: socket.socket, parts: list, authenticated: bool) -> None:

    global clients
    global client_sockets

    if not authenticated:
        send_error(client_socket, "BAD-RQST-HDR\n")
        return

    if len(parts) != 2:
        send_error(client_socket, "BAD-RQST-BODY\n")
        return

    # Split recipient and message
    message_parts = parts[1].split(' ', 1)
    if len(message_parts) != 2:
        send_error(client_socket, "BAD-RQST-BODY\n")
        return

    dest_user, message = message_parts

    # Check if message is empty or only whitespace
    if not message.strip():
        send_error(client_socket, "BAD-RQST-BODY\n")
        return

    # Check if destination user exists
    if dest_user not in clients:
        send_error(client_socket, "BAD-DEST-USER\n")
        return

    # Get sender username
    sender_username, _ = client_sockets[client_socket]

    # Send message to recipient
    recipient_socket = clients[dest_user]
    send_message(recipient_socket, f"DELIVERY {sender_username} {message}\n")

    # Confirm to sender
    send_message(client_socket, "SEND-OK\n")


def process_message(client_socket: socket.socket, message: str) -> None:

    username, authenticated = client_sockets.get(client_socket, (None, False))

    # Split message into command and parameters
    parts = message.split(' ', 1)
    if not parts:
        send_error(client_socket, "BAD-RQST-HDR\n")
        return

    command = parts[0]

    if command == "HELLO-FROM":
        handle_hello_from(client_socket, parts, authenticated)
    elif command == "LIST":
        handle_list(client_socket, authenticated)
    elif command == "SEND":
        handle_send(client_socket, parts, authenticated)
    else:
        send_error(client_socket, "BAD-RQST-HDR\n")


def handle_client(client_socket: socket.socket) -> None:

    global running
    global client_sockets

    buffer = b''

    try:
        while running:
            try:
                data = client_socket.recv(1)
                if not data:
                    break

                buffer += data

                while b'\n' in buffer:
                    message, buffer = buffer.split(b'\n', 1)
                    message = message.decode('utf-8')
                    process_message(client_socket, message)

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error handling client: {e}")
                break

    except Exception as e:
        logger.error(f"Client handler error: {e}")
    finally:
        disconnect_client(client_socket)


def cleanup() -> None:

    global running
    global client_sockets
    global server_socket

    running = False
    if server_socket:
        server_socket.close()
    for client_socket in list(client_sockets.keys()):
        try:
            client_socket.close()
        except Exception as e:
            logger.error(f"Error closing client socket: {e}")


# Execute using `python -m a3_chat_server`
def main() -> None:
    args: Namespace = parse_arguments()
    port: int = args.port
    host: str = args.address

    global server_socket
    global running
    global client_sockets

    # Start the chat server
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(5)
        logger.info(f"Server started on {host} port {port}")

        while running:
            readable, _, _ = select.select([server_socket], [], [], 1)
            for sock in readable:
                if sock == server_socket:
                    client_socket, address = server_socket.accept()
                    logger.info(f"New connection from {address}")
                    client_sockets[client_socket] = (None, False)
                    threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()

    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
