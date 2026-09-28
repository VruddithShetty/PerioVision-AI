"""Seed synthetic demo data (patients, visits, reviews, a signed report).

In demo mode (DB_MODE=demo) the backend seeds itself automatically at startup,
because the demo database lives in memory. Use this script to seed a real
MongoDB (DB_MODE=production), for example for a presentation machine:
    cd backend && python scripts/seed_demo_data.py [--force]
Also writes a few tiny synthetic sample images to data/sample/.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app import config, create_app  # noqa: E402
from app.ml import synthetic  # noqa: E402


def write_samples() -> list[str]:
    out = config.PROJECT_ROOT / "data" / "sample"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, levels in (("synthetic_mild.png", [8] * 12), ("synthetic_moderate.png", [22] * 12),
                         ("synthetic_severe.png", [40] * 12)):
        (out / name).write_bytes(synthetic.to_png(synthetic.make_radiograph(levels, seed=len(written))))
        written.append(str(out / name))
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="seed again even if demo data exists")
    args = ap.parse_args()
    os.environ["SEED_DEMO_DATA"] = "0"  # seed explicitly below, not in create_app
    create_app()
    from app.services.demo_seed import seed

    print(seed(force=args.force))
    for path in write_samples():
        print("sample image:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
