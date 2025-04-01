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


def send(string_bytes,sock):
    bytes_len = len(string_bytes)
    num_bytes_to_send = bytes_len
    while num_bytes_to_send > 0:
        num_bytes_to_send -= sock.send(string_bytes[bytes_len - num_bytes_to_send:])

    data = sock.recv(4096)
    if not data:
        return False
    else:
        return data.decode("utf-8")

def messaging(sock):
    userInput = input()

    handleInput = userInput.split(" ", 1)

    if len(handleInput) == 2:
        dest_user, message = handleInput
        dest_user = dest_user.removeprefix('@')
        string_bytes_message = f"SEND {dest_user} {message}\n".encode("utf-8")

        response_mess_sent = send(string_bytes_message, sock)

        # Success SENT
        if response_mess_sent == "SEND-OK\n":
            print("Sent")

        elif response_mess_sent == "BAD-DEST-USER\n":
            print("The destination user does not exist")

        else:
            print("Incorrect input !")
    elif len(handleInput) == 1:
        if userInput == "!who":
            users = getonline(sock)
            if users != False:
                print(f'There are {len(users)} online users:')
                for user in users:
                    print(user + "\n")

        else:
            print("Incorrect input !")
    else:
        print("Incorrect input !")

    # Different Thread

def recieving(sock):
    while True:
        if not False:
            rdlist, wrlist, exlist = select.select([sock], [], [])
            for client in rdlist:
                message = client.recv(4096).decode("utf-8")
                print(message)
        else:
            break

def getonline(sock):
    users = []
    string_bytes_get_users = f"LIST\n".encode("utf-8")

    response_all_users = send(string_bytes_get_users, sock)

    if "LIST-OK" in response_all_users:
        users_str = response_all_users[8:].strip()
        users = users_str.split(",")
        return users
    else:
        return False

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
    print("Welcome to Chat Client. Enter your login:")
    username = input()

    for letter in username:
        if letter in malformed:
            print(f"Cannot log in as {username}. That username contains disallowed characters.")
            return

    # Send Username to server
    string_bytes_2 = f"HELLO-FROM {username}\n".encode("utf-8")

    response_login_attempt = send(string_bytes_2,sock)

    if not response_login_attempt:
        print("Socket is closed")

    elif response_login_attempt == "IN-USE\n":
        print("Cannot log in as <username>. That username is already in use.")

    elif response_login_attempt == "BUSY\n":
        print("Cannot log in. The server is full!")

    #Success LOGIN
    elif response_login_attempt == f"HELLO {username}\n":
        print(f"Successfully logged in as {username}")
        t = threading.Thread(target=messaging, args=(sock,))
        t_2 = threading.Thread(target=recieving, args=(sock,))

        t.start()
        t_2.start()




if __name__ == "__main__":
    main()
