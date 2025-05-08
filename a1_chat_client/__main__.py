from argparse import Namespace, ArgumentParser
import socket
import threading
import select


def parse_arguments() -> Namespace:
    """
    Parse command line arguments for the chat client.
    The two valid options are:
        --address: The host to connect to. Default is "0.0.0.0"
        --port: The port to connect to. Default is 5378
    :return: The parsed arguments in a Namespace object.
    """

    parser: ArgumentParser = ArgumentParser(
        prog="python -m a1_chat_client",
        description="A1 Chat Client assignment for the VU Computer Networks course.",
        epilog="Authors: Your group name"
    )
    parser.add_argument("-a", "--address",
                      type=str, help="Set server address", default="0.0.0.0")
    parser.add_argument("-p", "--port",
                      type=int, help="Set server port", default=5378)
    return parser.parse_args()


def send(string_bytes, sock, isMain=False):
    # Send the data
    bytes_len = len(string_bytes)
    num_bytes_to_send = bytes_len
    while num_bytes_to_send > 0:
        num_bytes_to_send -= sock.send(string_bytes[bytes_len - num_bytes_to_send:])

    if isMain:
        total_data = b''
        while True:
            data = sock.recv(1)
            if not data:
                return False

            total_data += data

            if total_data.endswith(b'\n'):
                break

        return total_data.decode("utf-8")

def messaging(sock):
    while True:
        userInput = input()

        if userInput == "!quit":
            return
        elif userInput == "!who":
            getonline(sock)
            

        else:

            handleInput = userInput.split(" ", 1)

            if(len(handleInput)):
                dest_user, message = handleInput
                dest_user = dest_user.removeprefix('@')
                string_bytes_message = f"SEND {dest_user} {message}\n".encode("utf-8")

                send(string_bytes_message, sock, False)

            else:
                print("Incorrect input !")



def recieving(sock):
    buffer = b""

    while True:
        rdlist, wrlist, exlist = select.select([sock], [], [])
        for client in rdlist:

            data = client.recv(1)
            if not data:
                return

            buffer += data

            while b'\n' in buffer:

                message_bytes, buffer = buffer.split(b'\n', 1)
                message = message_bytes.decode("utf-8") + '\n'

                if message.startswith("DELIVERY"):

                    parts = message.split(" ", 2)
                    if len(parts) >= 3:
                        sender = parts[1]
                        content = parts[2].strip()
                        print(f"From {sender}: {content}")
                elif message == "BAD-RQST-HDR\n":
                    print("Error: Unknown issue in previous message header.")
                elif message == "BAD-RQST-BODY\n":
                    print("Error: Unknown issue in previous message body.")

                elif message == "SEND-OK\n":
                    print("The message was sent successfully")

                elif message == "BAD-DEST-USER\n":
                    print("The destination user does not exist")

                elif "LIST-OK" in message:
                    users_str = message[8:].strip()
                    users = users_str.split(",")
                    print(f'There are {len(users)} online users:')
                    for user in users:
                        print(user)




def getonline(sock):
    users = []
    string_bytes_get_users = f"LIST\n".encode("utf-8")

    send(string_bytes_get_users, sock, False)



# Execute using `python -m a1_chat_client`
def main() -> None:
    args: Namespace = parse_arguments()
    port: int = args.port
    host: str = args.address

    # TODO: Your implementation here

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))

    malformed = ['!','@','#','$','%','^','&','*']

    # 1.)
    print("Welcome to Chat Client. Enter your login: ")
    authed = False
    while not authed:

        username = input()

        if username == "!quit":
            break
        else:
            found = False
            for letter in username:
                if letter in malformed:
                    print(f"Cannot log in as {username}. That username contains disallowed characters.")
                    found = True

            if not found:

                # Send Username to server
                string_bytes_2 = f"HELLO-FROM {username}\n".encode("utf-8")

                response_login_attempt = send(string_bytes_2,sock, True)

                if not response_login_attempt:
                    print("Socket is closed")

                elif response_login_attempt == "IN-USE\n":
                    print(f"Cannot log in as {username}. That username is already in use. \n")

                elif response_login_attempt == "BUSY\n":
                    print("Cannot log in. The server is full! \n")

                elif response_login_attempt == "BAD-RQST-HDR\n":
                    print("Error: Unknown issue in previous message header.")

                elif response_login_attempt == "BAD-RQST-BODY\n":
                    print("Error: Unknown issue in previous message body.")

                #Success LOGIN
                elif response_login_attempt == f"HELLO {username}\n":
                    print(f"Successfully logged in as {username}!")
                    authed = True
                    t = threading.Thread(target=messaging, args=(sock,), daemon=False)
                    t_2 = threading.Thread(target=recieving, args=(sock,), daemon=True)

                    t.start()
                    t_2.start()


                    break

    return


if __name__ == "__main__":
    main()
