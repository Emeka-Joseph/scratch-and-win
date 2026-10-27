"""Production entry point, e.g.  waitress-serve --port=8000 wsgi:app   or   gunicorn wsgi:app"""
from app import create_app

app = create_app()
