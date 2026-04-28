import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WORKDIR = Path.cwd()
SESSIONS_DIR = WORKDIR / "sessions"

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

MAX_FILE_CHARS = 50000
