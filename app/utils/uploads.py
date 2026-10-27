import secrets

from flask import current_app
from werkzeug.utils import secure_filename


def save_image(file_storage, subfolder):
    """Save an uploaded image under static/uploads/<subfolder>; returns the static-relative path or None."""
    if not file_storage or not file_storage.filename:
        return None
    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXT"]:
        raise ValueError("Unsupported image type. Use PNG, JPG, WEBP or SVG.")
    folder = current_app.config["UPLOAD_FOLDER"] / subfolder
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}.{ext}"
    file_storage.save(folder / name)
    return f"uploads/{subfolder}/{name}"
