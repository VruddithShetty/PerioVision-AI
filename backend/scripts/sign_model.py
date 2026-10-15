"""Sign model weights into weights/manifest.json, with an RSA-PSS signature over it.

The manifest carries the SHA-256 of every weight file and, from config/model_approvals.json,
each model's identity, version, build provenance and clinical approval. The registry
needs both: a valid signature proves the file is unaltered, the provenance proves it is
the model this deployment is approved to run.

Each signing increments manifest_version. The registry records the highest version it
has accepted and refuses anything older, so an archived bundle - old weights plus their
own still-valid signature - cannot be replayed.

Usage (from the backend/ folder):
    python scripts/sign_model.py                 # sign weights/ with the approvals file
    python scripts/sign_model.py --no-provenance # hashes only (legacy; the registry will refuse)
    python scripts/sign_model.py --verify        # check every file against the signed manifest
    python scripts/sign_model.py --init-keys     # create a new key pair (only if none exists)
Needs MODEL_SIGNING_PASSWORD in the root .env.
"""
import argparse
import json
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
    parser.add_argument("--approvals", default=str(config.BACKEND_DIR / "config" / "model_approvals.json"),
                        help="provenance and approval metadata to sign into the manifest")
    parser.add_argument("--no-provenance", action="store_true",
                        help="sign hashes only; the registry refuses such a manifest")
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
        models = None
        if not args.no_provenance:
            try:
                with open(args.approvals, encoding="utf-8") as f:
                    models = json.load(f).get("models")
            except (OSError, ValueError) as exc:
                print(f"ERROR: could not read {args.approvals}: {exc}")
                return 2
            if not models:
                print(f"ERROR: {args.approvals} declares no models.")
                return 2

        # Signed twice, deliberately. Recording the self-check outputs runs the real
        # models, so they must already pass both gates - hence the first signing, which
        # carries the provenance the registry demands. Recording then writes
        # canary_expected.json into weights/, and that file is itself signed, so the
        # manifest has to be rebuilt over it.
        signer.sign_manifest(args.weights, models=models)
        if os.path.abspath(args.weights) == os.path.abspath(str(config.WEIGHTS_DIR)):
            try:
                from app.ml import canary
                from app.services import container

                container.reset_models()
                canary.record()
                print("Recorded the model self-check outputs (canary_expected.json)")
            except Exception as exc:
                print(f"WARNING: self-check outputs not recorded ({exc})")
        manifest = signer.sign_manifest(args.weights, models=models)
        for rel, info in manifest["files"].items():
            print(f"signed  {rel}  sha256={info['sha256'][:16]}...")
        for name, meta in (manifest.get("models") or {}).items():
            state = str(meta.get("approval_status", "?")).upper()
            mark = "OK " if state == "APPROVED" else "!! "
            print(f"{mark}{name:<16} v{meta.get('model_version')}  {state}")
        if manifest.get("models"):
            print(f"manifest_version = {manifest['manifest_version']} "
                  "(the registry refuses anything older than the newest it has accepted)")
            unapproved = [n for n, m in manifest["models"].items()
                          if str(m.get("approval_status", "")).lower() != "approved"]
            if unapproved:
                print(f"NOTE: not approved, so the registry will refuse to load: {', '.join(unapproved)}")
        else:
            print("NOTE: signed without provenance; the registry will refuse every model in it.")
        print(f"Manifest and signature written to {args.weights}. Public key fingerprint: {signer.public_key_fingerprint()}")
        return 0
    except SigningError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
