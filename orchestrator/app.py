#app.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Flask development server runs on port 5000 by default
    # Host '0.0.0.0' makes it accessible from other machines/WSL
    app.run(host='0.0.0.0', port=5000, debug=True)