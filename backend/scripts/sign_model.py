"""Sign model weights: writes weights/manifest.json (SHA-256 of every weight file) and an RSA-PSS signature.

Usage (from the backend/ folder):
    python scripts/sign_model.py              # sign everything in weights/
    python scripts/sign_model.py --verify     # check every file against the signed manifest
    python scripts/sign_model.py --init-keys  # create a new key pair (only if none exists)
Needs MODEL_SIGNING_PASSWORD in the root .env.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app import config  # noqa: E402
from app.security.model_signing import EXTERNAL_FILES, Signer, SigningError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weights", default=str(config.WEIGHTS_DIR))
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--init-keys", action="store_true")
    args = parser.parse_args()
    signer = Signer()
    try:
        if args.init_keys:
            signer.generate_keypair()
            print(f"Created key pair in {signer.keys_dir}")
            return 0
        if args.verify:
            manifest = signer.build_manifest(args.weights)
            bad = 0
            for rel in manifest["files"]:
                path = EXTERNAL_FILES.get(rel) or os.path.join(args.weights, rel)
                res = signer.verify_weight_file(path, args.weights)
                print(("OK      " if res["verified"] else "FAILED  ") + rel + ("" if res["verified"] else f"  ({res['reason']})"))
                bad += not res["verified"]
            return 1 if bad else 0
        signer.sign_manifest(args.weights)              # models must verify before their outputs are recorded
        if os.path.abspath(args.weights) == os.path.abspath(str(config.WEIGHTS_DIR)):
            try:
                from app.ml import canary
                from app.services import container

                container.reset_models()
                canary.record()
                print("Recorded the model self-check outputs (canary_expected.json)")
            except Exception as exc:
                print(f"WARNING: self-check outputs not recorded ({exc})")
        manifest = signer.sign_manifest(args.weights)
        for rel, info in manifest["files"].items():
            print(f"signed  {rel}  sha256={info['sha256'][:16]}...")
        print(f"Manifest and signature written to {args.weights}. Public key fingerprint: {signer.public_key_fingerprint()}")
        return 0
    except SigningError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
