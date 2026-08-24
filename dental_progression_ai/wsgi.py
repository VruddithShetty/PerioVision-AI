import os
import sys
import logging

# Ensure src directory is on import path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))
sys.path.insert(0, ROOT_DIR)

from server import app

# Set production environment variables fallback if missing
if "FIELD_ENCRYPTION_KEY" not in os.environ:
    os.environ["FIELD_ENCRYPTION_KEY"] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
if "WATERMARK_SECRET_KEY" not in os.environ:
    os.environ["WATERMARK_SECRET_KEY"] = "super-secret-watermark-key-12345"
if "MODEL_SIGNING_PASSWORD" not in os.environ:
    os.environ["MODEL_SIGNING_PASSWORD"] = "SuperSecureSigningPassword123!"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PerioVisionWSGI")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"Starting PerioVision AI Production Server on {host}:{port}...")
    app.run(host=host, port=port, debug=False)
