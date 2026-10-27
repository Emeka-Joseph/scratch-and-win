"""cPanel ("Setup Python App") entry point. Passenger looks for a WSGI callable named `application` here.

In cPanel set:  Application startup file = passenger_wsgi.py   Application Entry point = application
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app  # noqa: E402

application = create_app()
