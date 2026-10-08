import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CORS_ORIGINS = os.environ["CORS_ORIGINS"].split(",")
APP_ENV = os.environ["APP_ENV"]
JWT_SECRET = os.environ["JWT_SECRET"]
ACCESS_TOKEN_MINUTES = int(os.environ["ACCESS_TOKEN_MINUTES"])
REFRESH_TOKEN_DAYS = int(os.environ["REFRESH_TOKEN_DAYS"])
COOKIE_SECURE = os.environ["COOKIE_SECURE"].lower() == "true"
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"].lower()
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]
SEED_DEMO_DATA = os.environ["SEED_DEMO_DATA"].lower() == "true"
