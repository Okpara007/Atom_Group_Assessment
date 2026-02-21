import os
from dotenv import load_dotenv

# Load environment variables from a .env file (for API keys, etc.)
load_dotenv()

# Configuration settings

# JWT Settings
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_default_jwt_secret")  # Make sure to set this in .env
JWT_EXPIRY = int(os.getenv("JWT_EXPIRY", 60))  # Expiry time in minutes (default to 60)

# Directory paths
UPLOADS_DIR = "data/uploads"  # Directory where uploaded files will be stored
DB_PATH = os.path.join("data/db", "app.db")  # SQLite database path

# OpenAI API Key (Do NOT hardcode it in code)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # This will be read from the .env file

# Ensure that necessary directories exist
os.makedirs(UPLOADS_DIR, exist_ok=True)