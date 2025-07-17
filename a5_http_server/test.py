import socket
import os
import threading
import datetime
import mimetypes
import signal
import sys
from urllib.parse import unquote
from argparse import Namespace, ArgumentParser

host: str='0.0.0.0'
port: int =8000
base_directory: str='a5_http_server/public'
server_socket = None
is_running = False


def parse_arguments() -> Namespace:
    """
    Parse command line arguments for the http server.
    The three valid options are:
        --address: The host to listen at. Default is "0.0.0.0"
        --port: The port to listen at. Default is 8000
        --directory: The directory to serve. Default is "data"
    :return: The parsed arguments in a Namespace object.
    """

    parser: ArgumentParser = ArgumentParser(
        prog="python -m a5_http_server",
        description="A5 HTTP Server assignment for the VU Computer Networks course.",
        epilog="Authors: Your group name"
    )
    parser.add_argument("-a", "--address",
                        type=str, help="Set server address", default="0.0.0.0")
    parser.add_argument("-p", "--port",
                        type=int, help="Set server port", default=8000)
    parser.add_argument("-d", "--directory",
                        type=str, help="Set the directory to serve", default="a5_http_server/public")

    return parser.parse_args()

def parse_request(request_data):
    """Parse the HTTP request headers."""
    request = {}

    # Split the request into lines
    lines = request_data.decode('utf-8', errors='replace').split('\r\n')

    if not lines:
        return request

    # Parse the request line
    request_line_parts = lines[0].split(' ')
    if len(request_line_parts) >= 3:
        request['method'] = request_line_parts[0]
        request['path'] = unquote(request_line_parts[1])
        request['version'] = request_line_parts[2]

        # Parse the headers
        for i in range(1, len(lines)):
            line = lines[i]
            if not line:  # Empty line indicates end of headers
                break

            if ':' in line:
                key, value = line.split(':', 1)
                request[key.strip()] = value.strip()

    return request

def send_response(client_socket, status_code, content, content_type, keep_alive=False):
    """Send an HTTP response."""
    status_message = {
        200: 'OK',
        201: 'Created',
        400: 'Bad Request',
        404: 'Not Found',
        500: 'Internal Server Error'
    }.get(status_code, 'Unknown')

    # Build the response headers
    headers = [
        f"HTTP/1.1 {status_code} {status_message}",
        f"Date: {datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}",
        f"Server: PythonHTTP/1.1",
        f"Content-Length: {len(content)}",
        f"Content-Type: {content_type}; charset=utf-8"
    ]

    if keep_alive:
        headers.append("Connection: keep-alive")
    else:
        headers.append("Connection: close")

    # Join headers and add empty line
    header_bytes = '\r\n'.join(headers).encode('utf-8') + b'\r\n\r\n'

    # Send headers
    client_socket.send(header_bytes)

    # Send content in chunks to avoid using sendall()
    content_length = len(content)
    offset = 0
    chunk_size = 4096

    while offset < content_length:
        end = min(offset + chunk_size, content_length)
        client_socket.send(content[offset:end])
        offset = end

def send_error_response(client_socket, status_code, keep_alive=False):

    global base_directory

    error_file_name = f"{status_code}.html"
    error_file_path = os.path.join(base_directory, error_file_name)

    if os.path.isfile(error_file_path):
        try:
            with open(error_file_path, "rb") as f:
                content = f.read()
            # Serve the custom page
            send_response(client_socket, status_code, content, "text/html", keep_alive)
            return
        except Exception as exc:
            # If reading the custom page fails, fall back to generic page
            print(f"Could not read custom error page {error_file_path}: {exc}")

    status_message = {
        400: "Bad Request",
        404: "Not Found",
        500: "Internal Server Error"
    }.get(status_code, "Unknown Error")

    content = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{status_code} {status_message}</title>
</head>
<body>
    <h1>{status_code} {status_message}</h1>
    <p>Sorry, an error occurred while processing your request.</p>
</body>
</html>""".encode("utf-8")

    send_response(client_socket, status_code, content, "text/html", keep_alive)


def handle_get_request(client_socket, request):

    global base_directory


    raw_path = request.get("path", "/")
    path = raw_path if raw_path.startswith("/") else "/" + raw_path

    file_path = os.path.normpath(os.path.join(base_directory, path.lstrip("/")))


    if os.path.isdir(file_path):
        index_path = os.path.join(file_path, "index.html")
        if os.path.isfile(index_path):
            file_path = index_path
        else:
            # Directory without index.html → 404
            send_error_response(
                client_socket,
                404,
                request.get("Connection", "").lower() == "keep-alive"
            )
            return

    if not os.path.isfile(file_path):
        send_error_response(
            client_socket,
            404,
            request.get("Connection", "").lower() == "keep-alive"
        )
        return

    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = "application/octet-stream"

    try:
        with open(file_path, "rb") as f:
            content = f.read()

        send_response(
            client_socket,
            200,
            content,
            content_type,
            request.get("Connection", "").lower() == "keep-alive"
        )

    except Exception as exc:
        print(f"Error reading file {file_path}: {exc}")
        send_error_response(
            client_socket,
            500,
            request.get("Connection", "").lower() == "keep-alive"
        )


def handle_client(client_socket, client_address):
    """Handle a client connection."""
    global is_running

    keep_alive = True

    while keep_alive and is_running:
        try:
            # Set a timeout for the client socket
            client_socket.settimeout(10.0)

            # Receive and parse the request
            request_data = b''
            while b'\r\n\r\n' not in request_data:
                chunk = client_socket.recv(1024)
                if not chunk:
                    keep_alive = False
                    break
                request_data += chunk

            if not request_data:
                keep_alive = False
                break

            # Parse the HTTP headers
            request = parse_request(request_data)

            if (
                    "method" not in request
                    or "path" not in request
                    or "version" not in request
                    or not request["path"].startswith("/")
                    or request["version"].upper() not in ("HTTP/1.0", "HTTP/1.1")
            ):
                # Malformed → 400
                send_error_response(client_socket, 400, keep_alive=False)
                continue

            # Check if the connection should be kept alive
            keep_alive = request.get('Connection', '').lower() == 'keep-alive'

            # Process the request
            if request['method'] == 'GET':
                handle_get_request(client_socket, request)
            else:
                # Method not supported, return 400
                send_error_response(client_socket, 400, keep_alive)

        except socket.timeout:
            keep_alive = False
        except Exception as e:
            print(f"Error handling client {client_address}: {e}")
            keep_alive = False

    try:
        client_socket.close()
    except:
        pass

def shutdown(self, signum, frame):

    print("\nShutting down the server...")
    self.is_running = False
    if self.socket:
        self.socket.close()
    sys.exit(0)

def cleanup():
    global server_socket

    if server_socket:
        server_socket.close()
        server_socket = None
    print("Server stopped.")

def startServer():
    global server_socket
    global host
    global port
    global is_running

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((host, port))
        server_socket.listen(5)  # Queue up to 5 connection requests
        is_running = True

        print(f"HTTP Server running on http://{host}:{port}")

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        while is_running:
            try:
                client_socket, client_address = server_socket.accept()
                # Start a new thread to handle the client connection
                client_thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                if is_running:
                    print(f"Error accepting connection: {e}")

    except Exception as e:
        print(f"Server error: {e}")
    finally:
        cleanup()

def main() -> None:
    global port
    global base_directory
    global host

    parser: Namespace = parse_arguments()
    port = parser.port
    host = parser.address
    base_directory = parser.directory

    # Your implementation here

    # Ensure document root exists
    if not os.path.exists(base_directory):
        os.makedirs(base_directory)

    # Add missing MIME types
    mimetypes.add_type('text/javascript', '.js')
    mimetypes.add_type('text/css', '.css')
    mimetypes.add_type('text/html', '.html')
    mimetypes.add_type('image/jpeg', '.jpeg')
    mimetypes.add_type('image/png', '.png')
    mimetypes.add_type('application/pdf', '.pdf')

    startServer()


if __name__ == "__main__":
    main()