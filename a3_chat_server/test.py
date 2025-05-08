from argparse import Namespace, ArgumentParser
import socket
import threading
import select
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
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


class ChatServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}  # username -> socket
        self.client_sockets = {}  # socket -> (username, authenticated)
        self.max_users = 16
        self.running = True

    def start(self):
        """Start the chat server."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            logger.info(f"Server started on {self.host}:{self.port}")

            while self.running:
                readable, _, _ = select.select([self.server_socket], [], [], 1)
                for sock in readable:
                    if sock == self.server_socket:
                        client_socket, address = self.server_socket.accept()
                        logger.info(f"New connection from {address}")
                        self.client_sockets[client_socket] = (None, False)
                        threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()

        except KeyboardInterrupt:
            logger.info("Server shutting down...")
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up server resources."""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        for client_socket in list(self.client_sockets.keys()):
            try:
                client_socket.close()
            except:
                pass

    def handle_client(self, client_socket):
        """Handle communication with a single client."""
        buffer = b''

        try:
            while self.running:
                try:
                    data = client_socket.recv(1)
                    if not data:
                        break

                    buffer += data

                    # Process complete messages (ending with \n)
                    while b'\n' in buffer:
                        message, buffer = buffer.split(b'\n', 1)
                        message = message.decode('utf-8')
                        self.process_message(client_socket, message)

                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Error handling client: {e}")
                    break

        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            self.disconnect_client(client_socket)

    def process_message(self, client_socket, message):
        """Process a message from a client."""
        username, authenticated = self.client_sockets.get(client_socket, (None, False))

        # Split message into command and parameters
        parts = message.split(' ', 1)
        if not parts:
            self.send_error(client_socket, "BAD-RQST-HDR\n")
            return

        command = parts[0]

        if command == "HELLO-FROM":
            self.handle_hello_from(client_socket, parts, authenticated)
        elif command == "LIST":
            self.handle_list(client_socket, authenticated)
        elif command == "SEND":
            self.handle_send(client_socket, parts, authenticated)
        else:
            self.send_error(client_socket, "BAD-RQST-HDR\n")

    def handle_hello_from(self, client_socket, parts, authenticated):
        """Handle HELLO-FROM login request."""
        if authenticated:
            self.send_error(client_socket, "BAD-RQST-HDR\n")
            return

        if len(parts) != 2:
            self.send_error(client_socket, "BAD-RQST-BODY\n")
            return

        username = parts[1].strip()

        # Check for illegal characters
        illegal_chars = '!@#$%^&* '
        if any(char in illegal_chars for char in username):
            self.send_error(client_socket, "BAD-RQST-BODY\n")
            return

        # Check if username is already in use
        if username in self.clients:
            self.send_error(client_socket, "IN-USE\n")
            return

        # Check if server is full
        if len(self.clients) >= self.max_users:
            self.send_error(client_socket, "BUSY\n")
            return

        # Successfully authenticate user
        self.clients[username] = client_socket
        self.client_sockets[client_socket] = (username, True)
        self.send_message(client_socket, f"HELLO {username}\n")
        logger.info(f"User {username} authenticated")

    def handle_list(self, client_socket, authenticated):
        """Handle LIST request for online users."""
        if not authenticated:
            self.send_error(client_socket, "BAD-RQST-HDR\n")
            return

        user_list = ",".join(self.clients.keys())
        self.send_message(client_socket, f"LIST-OK {user_list}\n")

    def handle_send(self, client_socket, parts, authenticated):
        """Handle SEND message request."""
        if not authenticated:
            self.send_error(client_socket, "BAD-RQST-HDR\n")
            return

        if len(parts) != 2:
            self.send_error(client_socket, "BAD-RQST-HDR\n")
            return

        # Parse recipient and message
        message_parts = parts[1].split(' ', 1)
        if len(message_parts) != 2:
            self.send_error(client_socket, "BAD-RQST-HDR\n")
            return

        dest_user, message = message_parts

        # Check if message is empty or only whitespace
        if not message.strip():
            self.send_error(client_socket, "BAD-RQST-HDR\n")
            return

        # Check if destination user exists
        if dest_user not in self.clients:
            self.send_error(client_socket, "BAD-DEST-USER\n")
            return

        # Get sender username
        sender_username, _ = self.client_sockets[client_socket]

        # Send message to recipient
        recipient_socket = self.clients[dest_user]
        self.send_message(recipient_socket, f"DELIVERY {sender_username} {message}\n")

        # Confirm to sender
        self.send_message(client_socket, "SEND-OK\n")

    def send_message(self, client_socket, message):
        """Send a message to a client."""
        try:
            message_bytes = message.encode('utf-8')
            bytes_len = len(message_bytes)
            bytes_sent = 0

            while bytes_sent < bytes_len:
                bytes_sent += client_socket.send(message_bytes[bytes_sent:])

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.disconnect_client(client_socket)

    def send_error(self, client_socket, error_message):
        """Send an error message to a client."""
        self.send_message(client_socket, error_message)

    def disconnect_client(self, client_socket):
        """Disconnect a client and clean up."""
        try:
            username, _ = self.client_sockets.get(client_socket, (None, False))
            if username:
                del self.clients[username]
                logger.info(f"User {username} disconnected")

            if client_socket in self.client_sockets:
                del self.client_sockets[client_socket]

            client_socket.close()
        except Exception as e:
            logger.error(f"Error disconnecting client: {e}")


# Execute using `python -m a3_chat_server`
def main() -> None:
    args: Namespace = parse_arguments()
    port: int = args.port
    host: str = args.address

    # Create and start the chat server
    server = ChatServer(host, port)
    server.start()


if __name__ == "__main__":
    main()