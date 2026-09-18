from datetime import datetime, timedelta
from config import DEVICE_TIMEOUT_MINUTES

_latest_data: dict[str, dict] = {}
_device_chat_map: dict[str, str] = {}
_last_plant: dict[str, dict] = {}  # chat_id -> останній результат розпізнавання

def save_reading(device_id: str, temperature: float, humidity: float) -> None:
    _latest_data[device_id] = {
        "temperature": temperature,
        "humidity": humidity,
        "timestamp": datetime.now(),
    }

def get_reading(device_id: str) -> dict | None:
    return _latest_data.get(device_id)

def is_stale(reading: dict) -> bool:
    return datetime.now() - reading["timestamp"] > timedelta(
        minutes=DEVICE_TIMEOUT_MINUTES
    )

def register_device(device_id: str, chat_id: str) -> None:
    _device_chat_map[device_id] = chat_id

def chat_for_device(device_id: str) -> str | None:
    return _device_chat_map.get(device_id)

def devices_for_chat(chat_id: str) -> list[str]:
    return [d for d, c in _device_chat_map.items() if c == chat_id]

def save_plant(chat_id: str, prediction: list[tuple[str, float]]) -> None:
    _last_plant[chat_id] = {
        "prediction": prediction,
        "timestamp": datetime.now(),
    }

def get_plant(chat_id: str) -> dict | None:
    return _last_plant.get(chat_id)