"""
Generates a self-signed TLS certificate for local/LAN development so that
browsers on *other* machines will allow microphone access (getUserMedia
requires a secure context: https://, or http://localhost on the machine
itself).

This cert is for development and small private networks only. Every
browser will show a one-time "this site isn't trusted" warning that
people must click through — that's expected for a self-signed cert.
For a publicly reachable site, use a real certificate instead (see
README.md's "Going public" section) and skip this script entirely.

Usage:
    python make_certs.py              # auto-detects your LAN IP
    python make_certs.py 192.168.1.42 # or pass it explicitly

Requires: pip install cryptography
"""

import datetime
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

OUT_DIR = Path(__file__).resolve().parent


def detect_lan_ip() -> str:
    """Best-effort guess at this machine's LAN IP (doesn't actually send traffic)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    lan_ip = sys.argv[1] if len(sys.argv) > 1 else detect_lan_ip()
    print(f"Generating a certificate valid for: localhost, 127.0.0.1, {lan_ip}")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "VoiceForge Local Dev"),
    ])

    san = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.IPAddress(ipaddress.ip_address(lan_ip)),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path = OUT_DIR / "dev.key"
    cert_path = OUT_DIR / "dev.crt"

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Wrote {key_path} and {cert_path}")
    print(f"\nStart the backend with:")
    print(f"  uvicorn main:app --host 0.0.0.0 --port 8000 --ssl-keyfile {key_path} --ssl-certfile {cert_path}")
    print(f"\nServe the frontend with:")
    print(f"  python serve_https.py")
    print(f"\nThen, from any PC on the same network, open:")
    print(f"  https://{lan_ip}:5173")
    print("Each browser will warn that the certificate isn't trusted — that's expected for a self-signed cert; click through to proceed.")


if __name__ == "__main__":
    main()
