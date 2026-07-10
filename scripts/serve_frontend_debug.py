import http.server
import os
import socket
import socketserver
import sys

HOST = "0.0.0.0"
PORT = 7777
DIRECTORY = os.path.join(os.path.dirname(__file__), "frontend_debug")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)


# Subclass TCPServer to prevent "Address already in use" errors on restart
class SafeTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def get_local_ip() -> str:
    """Helper to detect the machine's primary local network IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This setup doesn't send data or need internet access;
        # it just determines which local interface is used to route traffic.
        s.connect(("10.255.255.255", 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()
    return local_ip


def run():
    if not os.path.exists(DIRECTORY):
        print(f"Error: Directory {DIRECTORY} does not exist.")
        sys.exit(1)

    local_ip = get_local_ip()

    with SafeTCPServer((HOST, PORT), Handler) as httpd:
        print(f"Serving debug frontend on your network:")
        print(f"  - On this machine: http://localhost:{PORT}")
        if local_ip != "127.0.0.1":
            print(f"  - On other devices: http://{local_ip}:{PORT}")
        else:
            print("  - On other devices: (Could not detect local IP)")
            
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()


if __name__ == "__main__":
    run()