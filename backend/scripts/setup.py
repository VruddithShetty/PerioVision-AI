import os
import sys

# Ensure root is in path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)  # backend/

def setup_environment():
    """Initializes folder structure and default security keys."""
    folders = [
        "storage/xrays",
        "storage/reports",
        "storage/models",
        "weights",
        "logs"
    ]
    for f in folders:
        os.makedirs(os.path.join(ROOT_DIR, f), exist_ok=True)
        print(f"Created/Verified: {f}")

    # Secrets are never generated with fixed values here.
    env_path = os.path.join(os.path.dirname(ROOT_DIR), ".env")
    if not os.path.exists(env_path):
        print("No .env found. Copy .env.example to .env at the repository root and fill in real values.")

if __name__ == "__main__":
    setup_environment()
