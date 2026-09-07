import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)
DOCS_DIR = BASE_DIR / "generated_docs"
DOCS_DIR.mkdir(exist_ok=True)

class Settings(BaseSettings):
    APP_NAME: str = "Kirana AI Store Manager"
    STORE_NAME: str = "Supermarket"
    STORE_ADDRESS: str = "12, Bazaar Main Road, Gandhinagar, Bengaluru, Karnataka 560009"
    STORE_GSTIN: str = "29AAAAA0000A1Z5"
    STORE_PHONE: str = "+91 98765 43210"
    DEFAULT_PAYMENT_MODE: str = "UPI"
    
    # Database
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATA_DIR}/kirana.db"
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    ALLOWED_TELEGRAM_USER_IDS: str = ""  # Comma separated telegram user IDs or empty for public
    
    # LLM (optional if using offline deterministic orchestrator)
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-3-5-sonnet-20241022"
    
    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8080
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
