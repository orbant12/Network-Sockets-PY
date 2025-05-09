import socket
import os
import threading
import datetime
import mimetypes
import signal
import sys
from urllib.parse import unquote
from argparse import Namespace, ArgumentParser


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


class HTTPServer:
    def __init__(self, host='0.0.0.0', port=8000, document_root='a5_http_server/public'):
        self.host = host
        self.port = port
        self.document_root = document_root
        self.socket = None
        self.is_running = False

        # Ensure document root exists
        if not os.path.exists(self.document_root):
            os.makedirs(self.document_root)

        # Add missing MIME types
        mimetypes.add_type('text/javascript', '.js')
        mimetypes.add_type('text/css', '.css')
        mimetypes.add_type('text/html', '.html')
        mimetypes.add_type('image/jpeg', '.jpeg')
        mimetypes.add_type('image/png', '.png')
        mimetypes.add_type('application/pdf', '.pdf')

    def start(self):
        """Start the HTTP server."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)  # Queue up to 5 connection requests
            self.is_running = True

            print(f"HTTP Server running on http://{self.host}:{self.port}")

            # Register signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self.shutdown)
            signal.signal(signal.SIGTERM, self.shutdown)

            while self.is_running:
                try:
                    client_socket, client_address = self.socket.accept()
                    # Start a new thread to handle the client connection
                    client_thread = threading.Thread(target=self.handle_client, args=(client_socket, client_address))
                    client_thread.daemon = True
                    client_thread.start()
                except Exception as e:
                    if self.is_running:
                        print(f"Error accepting connection: {e}")

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.cleanup()

    def handle_client(self, client_socket, client_address):
        """Handle a client connection."""
        keep_alive = True

        while keep_alive and self.is_running:
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
                request = self.parse_request(request_data)

                # Check if the connection should be kept alive
                keep_alive = request.get('Connection', '').lower() == 'keep-alive'

                # Process the request
                if request['method'] == 'GET':
                    self.handle_get_request(client_socket, request)
                else:
                    # Method not supported, return 400
                    self.send_error_response(client_socket, 400, keep_alive)

            except socket.timeout:
                keep_alive = False
            except Exception as e:
                print(f"Error handling client {client_address}: {e}")
                keep_alive = False

        try:
            client_socket.close()
        except:
            pass

    def parse_request(self, request_data):
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

    def handle_get_request(self, client_socket, request):
        """Handle a GET request."""
        path = request['path']

        # If path is root, serve index.html
        if path == '/':
            path = '/index.html'

        # Normalize the path to prevent directory traversal
        file_path = os.path.normpath(os.path.join(self.document_root, path.lstrip('/')))

        # Ensure the path is within the document root
        if not file_path.startswith(self.document_root):
            self.send_error_response(client_socket, 400, request.get('Connection', '').lower() == 'keep-alive')
            return

        # Check if the file exists
        if not os.path.isfile(file_path):
            self.send_error_response(client_socket, 404, request.get('Connection', '').lower() == 'keep-alive')
            return

        # Get the file's MIME type
        content_type, encoding = mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'

        # Read the file
        try:
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # Send 200 OK response
            self.send_response(client_socket, 200, file_content, content_type,
                               request.get('Connection', '').lower() == 'keep-alive')

        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            self.send_error_response(client_socket, 500, request.get('Connection', '').lower() == 'keep-alive')

    def send_response(self, client_socket, status_code, content, content_type, keep_alive=False):
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
            f"Date: {self.get_date_header()}",
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

    def send_error_response(self, client_socket, status_code, keep_alive=False):
        """Send an error response."""
        if status_code == 404:
            # Try to serve 404.html
            error_file_path = os.path.join(self.document_root, '404.html')
            if os.path.isfile(error_file_path):
                with open(error_file_path, 'rb') as f:
                    content = f.read()
                self.send_response(client_socket, 404, content, 'text/html', keep_alive)
                return

        # If no custom error page available, send a default error message
        status_message = {
            400: 'Bad Request',
            404: 'Not Found',
            500: 'Internal Server Error'
        }.get(status_code, 'Unknown Error')

        content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>{status_code} {status_message}</title>
        </head>
        <body>
            <h1>{status_code} {status_message}</h1>
            <p>Sorry, an error occurred.</p>
        </body>
        </html>
        """.encode('utf-8')

        self.send_response(client_socket, status_code, content, 'text/html', keep_alive)

    def get_date_header(self):
        """Return a date string in HTTP header format."""
        return datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')

    def shutdown(self, signum, frame):
        """Shutdown the server gracefully."""
        print("\nShutting down the server...")
        self.is_running = False
        if self.socket:
            self.socket.close()
        sys.exit(0)

    def cleanup(self):
        """Clean up server resources."""
        if self.socket:
            self.socket.close()
            self.socket = None
        print("Server stopped.")


def main() -> None:
    args: Namespace = parse_arguments()
    port: int = args.port
    host: str = args.address
    base_directory: str = args.directory

    # Create and start the HTTP server
    server = HTTPServer(host=host, port=port, document_root=base_directory)
    server.start()


if __name__ == "__main__":
    main()