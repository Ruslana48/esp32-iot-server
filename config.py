import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

CONTROL_TEMP = 24.0
CONTROL_HUMIDITY = 50.0
TEMP_ALLOWED_DIFF = 5.0
HUMIDITY_ALLOWED_DIFF = 15.0

DEVICE_TIMEOUT_MINUTES = 5

MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "models" / "plant_classifier.pt"))
TOP_K = 3

CONFIDENCE_THRESHOLD = 0.60