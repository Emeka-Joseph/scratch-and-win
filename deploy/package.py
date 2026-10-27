"""Build the zip to upload to cPanel:  python deploy/package.py   ->  dist/razzmattazz_promo_<date>.zip

Leaves out secrets (.env), the local SQLite database, uploaded logos, tests and caches,
so a re-upload never overwrites live data.
"""
import fnmatch
import os
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", ".idea", ".vscode", "venv", ".venv",
                "instance", "dist", "tests", "tmp"}
EXCLUDE_FILES = [".env", "*.pyc", "*.bak", "*.db", "*.log", "roadmap.jpeg", ".DS_Store", "Thumbs.db"]
UPLOADS = os.path.join("app", "static", "uploads")


def wanted(rel_path):
    name = os.path.basename(rel_path)
    if any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_FILES):
        return False
    return not rel_path.startswith(UPLOADS + os.sep)


def main():
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    target = os.path.join(ROOT, "dist", f"razzmattazz_promo_{datetime.now():%Y%m%d_%H%M}.zip")
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                rel = os.path.relpath(os.path.join(folder, f), ROOT)
                if wanted(rel):
                    zf.write(os.path.join(ROOT, rel), rel.replace(os.sep, "/"))
                    count += 1
        # keep the (empty) uploads folders so the app can write logos on first use
        for sub in ("logos", "prizes"):
            zf.writestr(f"app/static/uploads/{sub}/.keep", "")
    print(f"{count} files -> {target}")


if __name__ == "__main__":
    main()
