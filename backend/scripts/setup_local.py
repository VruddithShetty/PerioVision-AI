"""First-time local setup for a fresh copy of the repository (git clone or GitHub ZIP). Safe to run again.

1. .env: if it does not exist, create it from .env.example with fresh random secrets, DB_MODE=demo and
   demo accounts (random passwords). The demo logins are printed and written to demo_logins.txt (gitignored).
   An existing .env is never changed.
2. Model weights: the repository ships the trained weights, a signed manifest and the publisher's public
   key. They are verified with that public key FIRST; only if every shipped file verifies does the script
   create this machine's own signing key (needed to sign PDF reports) and re-sign the verified weights with
   it. A weight file that fails verification stops the script, so a tampered copy is never re-signed.
   An existing local signing key is never replaced.

Usage (from the repository root):  python backend/scripts/setup_local.py
"""
import re
import secrets
import shutil
import string
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
ENV, EXAMPLE = ROOT / ".env", ROOT / ".env.example"
DEMO_ROLES = {"DEMO": "dentist", "DEMO_ADMIN": "admin", "DEMO_TECHNICIAN": "technician", "DEMO_AUDITOR": "auditor"}


def demo_password() -> str:
    # 14 chars with upper, lower and digit (the app's password rule)
    while True:
        p = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12)) + "A7"
        if any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p):
            return p


def make_env() -> None:
    if ENV.exists():
        print(".env already exists - left unchanged.")
        return
    text = EXAMPLE.read_text(encoding="utf-8")
    values = {"DB_MODE": "demo"}
    for key in ("JWT_SECRET_KEY", "FIELD_ENCRYPTION_KEY", "AUDIT_ANCHOR_KEY"):
        values[key] = secrets.token_hex(32)
    values["MODEL_SIGNING_PASSWORD"] = secrets.token_urlsafe(24)
    values["MONGO_ROOT_PASSWORD"] = secrets.token_urlsafe(18)
    logins = []
    for prefix, role in DEMO_ROLES.items():
        if re.search(rf"^{prefix}_EMAIL=", text, re.M) or prefix == "DEMO":
            email, pw = f"{role}@demo.periovision.local", demo_password()
            values[f"{prefix}_EMAIL"], values[f"{prefix}_PASSWORD"] = email, pw
            logins.append((role, email, pw))
    lines, seen = [], set()
    for line in text.splitlines():
        m = re.match(r"^([A-Z0-9_]+)=", line)
        if m and m.group(1) in values:
            lines.append(f"{m.group(1)}={values[m.group(1)]}")
            seen.add(m.group(1))
        else:
            lines.append(line)
    lines += [f"{k}={v}" for k, v in values.items() if k not in seen]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    note = ["PerioVision demo logins (local only; also in .env):"] + [f"  {r:<11} {e}   {p}" for r, e, p in logins]
    (ROOT / "demo_logins.txt").write_text("\n".join(note) + "\n", encoding="utf-8")
    print("Created .env with fresh random secrets (demo mode).")
    print("\n".join(note))


def setup_keys() -> int:
    from dotenv import load_dotenv

    load_dotenv(ENV, override=True)
    sys.path.insert(0, str(BACKEND))
    from app import config
    from app.security.model_signing import Signer

    signer = Signer()
    if signer.priv_path.exists():
        print("Local signing key already present - weights and keys left unchanged.")
        return 0
    weights = Path(config.WEIGHTS_DIR)
    manifest = weights / "manifest.json"
    shipped = []
    if manifest.exists() and signer.pub_path.exists():
        import json

        for rel in json.loads(manifest.read_text(encoding="utf-8"))["files"]:
            path = weights / rel
            if not path.exists():
                continue                    # files the publisher kept locally are simply not shipped
            if path.stat().st_size < 1024 and path.read_bytes().startswith(b"version https://git-lfs"):
                print(f"ERROR: {rel} is a Git LFS pointer, not the model. Download the real file and run again.")
                return 2
            res = signer.verify_weight_file(path, weights)
            if not res.get("verified"):
                print(f"ERROR: shipped weight file {rel} failed verification ({res.get('reason')}). Nothing was changed.")
                return 2
            shipped.append(rel)
        print(f"Verified {len(shipped)} shipped weight file(s) with the publisher's public key.")
        shutil.copy(signer.pub_path, signer.pub_path.with_name("publisher_model_signing.pub"))
    signer.generate_keypair()
    print("Created this machine's signing key (backend/keys/model_signing.pem, protected by MODEL_SIGNING_PASSWORD).")
    if shipped:
        signer.sign_manifest(weights)
        print("Re-signed the verified weights with the local key.")
    else:
        print("No shipped weights found: the app runs in labelled demo mode until models are installed.")
    return 0


def main() -> int:
    if not EXAMPLE.exists():
        print("ERROR: run this from a full copy of the repository (.env.example not found).")
        return 2
    make_env()
    return setup_keys()


if __name__ == "__main__":
    raise SystemExit(main())
