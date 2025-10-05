# engine/render_batch.py
from __future__ import annotations
import json, sys
from pathlib import Path

from engine import ROOT               # now we get ROOT from engine/__init__.py
from engine.render_job import render as render_one

def load_job_file(path: Path) -> dict:
    return json.loads(path.read_text())

def main() -> None:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python engine/render_batch.py <jobs_dir> [limit]")
        sys.exit(2)

    jobs_dir = (ROOT / sys.argv[1]).resolve()
    if not jobs_dir.exists() or not jobs_dir.is_dir():
        print(f"❌ Not a directory: {jobs_dir}")
        sys.exit(1)

    limit = int(sys.argv[2]) if len(sys.argv) == 3 else None

    job_files = sorted(
        list(jobs_dir.glob("*.json")) +
        list(jobs_dir.glob("*.JSON"))
    )
    
    if not job_files:
        print(f"⚠️ No .json jobs found in {jobs_dir}")
        sys.exit(0)
    if limit is not None:
        job_files = job_files[:limit]

    total, ok, fail = len(job_files), 0, 0
    print(f"📦 Found {total} job(s) in {jobs_dir}\n")

    for idx, job_path in enumerate(job_files, start=1):
        print(f"[{idx}/{total}] Rendering {job_path.name} ...")
        try:
            job = load_job_file(job_path)
            render_one(job)
            ok += 1
        except Exception as e:
            print(f"   ❌ {job_path.name}: {e}")
            fail += 1

    print("\n— Summary —")
    print(f"✅ Success: {ok}")
    print(f"❌ Failed : {fail}")

if __name__ == "__main__":
    main()
