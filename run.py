"""Development entry point:  python run.py   (or: flask --app run run --debug)"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "9800")), debug=True)
