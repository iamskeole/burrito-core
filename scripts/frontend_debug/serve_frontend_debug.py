import http.server
import socketserver
import os
import sys

PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(__file__), "")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def run():
    if not os.path.exists(DIRECTORY):
        print(f"Error: Directory {DIRECTORY} does not exist.")
        sys.exit(1)
        
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving debug frontend at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()

if __name__ == "__main__":
    run()
