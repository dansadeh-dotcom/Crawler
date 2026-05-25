"""
Vercel serverless handler for the Flask app.
This file is required by Vercel's Python runtime.
Exports the Flask WSGI application for Vercel to route requests through.
"""

import sys
import os

# Add parent directory to path so we can import app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel expects the WSGI app to be named 'app'
# The Flask app object itself is a WSGI application

