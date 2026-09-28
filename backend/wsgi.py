"""Backend entry point: `python wsgi.py` (from the backend/ folder) or any WSGI server (`wsgi:app`).

HTTPS for local demos: run `python scripts/make_dev_cert.py`, then set TLS_CERT and TLS_KEY in .env.
In production, terminate TLS at a reverse proxy instead of using the development server.
"""
import os

from app import config, create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"  # never enable on a shared network
    cert, key = os.environ.get("TLS_CERT"), os.environ.get("TLS_KEY")
    ssl_context = None
    if cert and key:
        resolve = lambda p: p if os.path.isabs(p) else str(config.BACKEND_DIR / p)  # noqa: E731
        ssl_context = (resolve(cert), resolve(key))
        print(f"Serving HTTPS on https://{host}:{port} (self-signed development certificate)")
    app.run(host=host, port=port, debug=debug, ssl_context=ssl_context)
