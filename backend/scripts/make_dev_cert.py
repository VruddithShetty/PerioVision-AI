"""Create a self-signed TLS certificate for local HTTPS demos (valid 30 days, localhost only).

    cd backend && python scripts/make_dev_cert.py
Then set TLS_CERT=keys/dev-tls.crt and TLS_KEY=keys/dev-tls.key in .env and start the backend:
it will serve https://127.0.0.1:5000. Browsers will warn that the certificate is self-signed;
that is expected for local development and must never be used in production.
"""
import datetime as dt
import ipaddress
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from app import config  # noqa: E402


def main() -> int:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PerioVision AI (development)")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + dt.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                    x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    config.KEYS_DIR.mkdir(parents=True, exist_ok=True)
    (config.KEYS_DIR / "dev-tls.key").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (config.KEYS_DIR / "dev-tls.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Wrote {config.KEYS_DIR / 'dev-tls.crt'} and dev-tls.key (gitignored). Valid until {now + dt.timedelta(days=30):%Y-%m-%d}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
