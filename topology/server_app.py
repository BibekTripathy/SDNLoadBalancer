"""
Lightweight Backend HTTP Server to run inside Mininet host namespaces.
"""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class BackendHTTPRequestHandler(BaseHTTPRequestHandler):
    server_name: str = "server1"
    simulated_delay: float = 0.0

    def do_GET(self):
        if self.simulated_delay > 0:
            time.sleep(self.simulated_delay)

        response_data = {
            "status": "OK",
            "server_id": self.server_name,
            "path": self.path,
            "timestamp": time.time(),
            "client_address": self.client_address[0],
        }

        body = json.dumps(response_data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Override to keep logs clean
        print(f"[{self.server_name}] {self.address_string()} - {format % args}")


def run_server(server_name: str, host: str = "0.0.0.0", port: int = 80, delay: float = 0.0):
    BackendHTTPRequestHandler.server_name = server_name
    BackendHTTPRequestHandler.simulated_delay = delay
    server_address = (host, port)
    httpd = HTTPServer(server_address, BackendHTTPRequestHandler)
    print(f"Starting backend HTTP server '{server_name}' on {host}:{port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"Stopping server '{server_name}'.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SDN Backend Host HTTP Server")
    parser.add_argument("--name", type=str, default="server1", help="Server identifier name")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=80, help="Listen port")
    parser.add_argument("--delay", type=float, default=0.0, help="Simulated processing delay in seconds")
    args = parser.parse_args()

    run_server(server_name=args.name, host=args.host, port=args.port, delay=args.delay)
