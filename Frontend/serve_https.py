"""
Serves frontend/ over HTTPS on 0.0.0.0:5173 using the certificate generated
by certs/make_certs.py, so other computers on the network can load the page
over a secure origin (required for microphone access).

Usage:
    python certs/make_certs.py      # once, from the project root
    cd frontend
    python serve_https.py

Then open https://<this-machine's-LAN-IP>:5173 from any device on the
same network.
"""

import http.server
import ssl
from pathlib import Path

PORT = 5173
FRONTEND_DIR = Path(__file__).resolve().parent
CERT_DIR = FRONTEND_DIR.parent / "certs"
CERTFILE = CERT_DIR / "dev.crt"
KEYFILE = CERT_DIR / "dev.key"


def main():
    if not CERTFILE.exists() or not KEYFILE.exists():
        raise SystemExit(
            f"Missing certificate. Run this first from the project root:\n"
            f"    python certs/make_certs.py"
        )

    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(("0.0.0.0", PORT), handler)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERTFILE), keyfile=str(KEYFILE))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print(f"Serving {FRONTEND_DIR} over HTTPS on port {PORT}")
    print(f"Open https://localhost:{PORT} or https://<this-machine's-LAN-IP>:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
