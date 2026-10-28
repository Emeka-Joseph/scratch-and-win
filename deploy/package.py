"""Build the zip to upload to cPanel:  python deploy/package.py   ->  dist/razzmattazz_promo_<date>.zip

Leaves out secrets (.env files), the local SQLite database, uploaded logos, tests and caches,
so a re-upload never overwrites live data.

    python deploy/package.py --with-env .env.production   # first upload: also ship that file as .env
"""
import fnmatch
import os
import sys
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", ".idea", ".vscode", "venv", ".venv",
                "instance", "dist", "tests", "tmp"}
EXCLUDE_FILES = [".env", ".env.*", "*.pyc", "*.bak", "*.db", "*.log", "roadmap.jpeg", ".DS_Store", "Thumbs.db"]
KEEP_FILES = {".env.example", ".env.production.example"}
UPLOADS = os.path.join("app", "static", "uploads")


def wanted(rel_path):
    name = os.path.basename(rel_path)
    if name in KEEP_FILES:
        return True
    if any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_FILES):
        return False
    if os.sep not in rel_path and name.lower().endswith((".png", ".jpg", ".jpeg")):
        return False   # screenshots in the project root (may show customer data)
    return not rel_path.startswith(UPLOADS + os.sep)


def main():
    env_file = sys.argv[sys.argv.index("--with-env") + 1] if "--with-env" in sys.argv else None
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    suffix = "_with_env" if env_file else ""
    target = os.path.join(ROOT, "dist", f"razzmattazz_promo_{datetime.now():%Y%m%d_%H%M}{suffix}.zip")
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
        if env_file:
            zf.write(os.path.join(ROOT, env_file), ".env")
            print(f"Included {env_file} as .env -- keep this zip private and delete it from the server after extracting.")
    print(f"{count} files -> {target}")


if __name__ == "__main__":
    main()
