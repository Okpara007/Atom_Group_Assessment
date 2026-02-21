import os
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_default_jwt_secret")
JWT_EXPIRY = int(os.getenv("JWT_EXPIRY", 60))
UPLOADS_DIR = "data/uploads"
DB_PATH = os.path.join("data/db", "app.db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
os.makedirs(UPLOADS_DIR, exist_ok=True)
