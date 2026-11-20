import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "local-dev-change-this-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'instance' / 'desperdicio_cero.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SCHEDULER_API_ENABLED = False
    EXTERNAL_DATA_URL = os.getenv("EXTERNAL_DATA_URL", "https://www.datosabiertos.gob.pe/api/3/action/package_search")
    CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
    SOCIAL_INSTAGRAM_URL = os.getenv("SOCIAL_INSTAGRAM_URL", "")
    SOCIAL_FACEBOOK_URL = os.getenv("SOCIAL_FACEBOOK_URL", "")
    SOCIAL_LINKEDIN_URL = os.getenv("SOCIAL_LINKEDIN_URL", "")
    CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
    SOCIAL_INSTAGRAM_URL = os.getenv("SOCIAL_INSTAGRAM_URL", "")
    SOCIAL_FACEBOOK_URL = os.getenv("SOCIAL_FACEBOOK_URL", "")
    SOCIAL_LINKEDIN_URL = os.getenv("SOCIAL_LINKEDIN_URL", "")
