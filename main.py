from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import plant_classifier
import storage
import telegram_api as tg
from config import (
    CONFIDENCE_THRESHOLD,
    CONTROL_HUMIDITY,
    CONTROL_TEMP,
    HUMIDITY_ALLOWED_DIFF,
    TEMP_ALLOWED_DIFF,
    TOP_K,
)

app = FastAPI(title="Plant monitoring system")

class SensorData(BaseModel):
    device_id: str
    temperature: float = Field(..., ge=-40, le=80)
    humidity: float = Field(..., ge=0, le=100)


@app.get("/")
def root():
    return {"message": "ESP32 IoT server works", "model_loaded": plant_classifier.is_ready()}


@app.post("/sensor-data")
def receive_data(data: SensorData):
    storage.save_reading(data.device_id, data.temperature, data.humidity)

    chat_id = storage.chat_for_device(data.device_id)
    temp_diff = abs(data.temperature - CONTROL_TEMP)
    hum_diff = abs(data.humidity - CONTROL_HUMIDITY)

    alert_sent = False
    if chat_id and (temp_diff > TEMP_ALLOWED_DIFF or hum_diff > HUMIDITY_ALLOWED_DIFF):
        tg.send_message(
            chat_id,
            f"Сповіщення від пристрою {data.device_id}\n"
            f"Температура: {data.temperature}°C (відхилення {temp_diff:.1f}°C)\n"
            f"Вологість: {data.humidity}% (відхилення {hum_diff:.1f}%)",
        )
        alert_sent = True

    print(f"Received from {data.device_id}: {data.temperature}°C, {data.humidity}%", flush=True)

    return {
        "status": "ok",
        "device_id": data.device_id,
        "temperature": data.temperature,
        "humidity": data.humidity,
        "alert_sent": alert_sent,
    }

@app.get("/latest/{device_id}")
def get_latest(device_id: str):
    reading = storage.get_reading(device_id)

    if reading is None:
        return {"device_id": device_id, "temperature": 0, "humidity": 0, "status": "no data"}

    if storage.is_stale(reading):
        return {"device_id": device_id, "temperature": 0, "humidity": 0, "status": "device offline"}

    return {
        "device_id": device_id,
        "temperature": reading["temperature"],
        "humidity": reading["humidity"],
        "status": "online",
    }

HELP_TEXT = (
    "Доступні команди:\n"
    "/register esp32_001 — прив'язати пристрій\n"
    "/status — останні показники сенсорів\n"
    "/help — довідка\n\n"
    "Або просто надішліть фото рослини — я спробую визначити її вид."
)

def handle_start(chat_id: str) -> None:
    tg.send_message(chat_id, "Вітаю! Я бот моніторингу кімнатних рослин.\n\n" + HELP_TEXT)

def handle_register(chat_id: str, text: str) -> None:
    parts = text.split()
    if len(parts) != 2:
        tg.send_message(chat_id, "Формат команди:\n/register esp32_001")
        return

    storage.register_device(parts[1], chat_id)
    tg.send_message(chat_id, f"Пристрій {parts[1]} успішно зареєстровано.")

def handle_status(chat_id: str) -> None:
    devices = storage.devices_for_chat(chat_id)
    if not devices:
        tg.send_message(chat_id, "Пристрій не зареєстровано. Використайте:\n/register esp32_001")
        return

    device_id = devices[0]
    reading = storage.get_reading(device_id)

    if reading is None:
        tg.send_message(chat_id, f"Даних від {device_id} ще не надходило.")
        return

    if storage.is_stale(reading):
        tg.send_message(chat_id, f"Пристрій {device_id} офлайн.")
        return

    tg.send_message(
        chat_id,
        f"Пристрій: {device_id}\n"
        f"Температура: {reading['temperature']}°C\n"
        f"Вологість: {reading['humidity']}%\n"
        f"Статус: онлайн",
    )

def format_species(raw: str) -> str:
    return raw.replace("_", " ").strip()

def handle_photo(chat_id: str, photo_sizes: list[dict]) -> None:
    if not plant_classifier.is_ready():
        tg.send_message(chat_id, "Модель розпізнавання ще не навчена. Спробуйте пізніше.")
        return

    tg.send_chat_action(chat_id, "typing")

    file_id = photo_sizes[-1]["file_id"]

    try:
        image_bytes = tg.download_file(file_id)
        predictions = plant_classifier.predict(image_bytes, top_k=TOP_K)
    except Exception as exc:
        print(f"Помилка розпізнавання: {exc}", flush=True)
        tg.send_message(chat_id, "Не вдалося обробити фото. Спробуйте ще раз.")
        return

    storage.save_plant(chat_id, predictions)

    top_name, top_prob = predictions[0]
    confident = top_prob >= CONFIDENCE_THRESHOLD

    if confident:
        lines = [
            f"Схоже, це: {format_species(top_name)}",
            f"Впевненість: {top_prob:.0%}",
        ]
        others = predictions[1:]
        header = "\nІнші варіанти:"
    else:
        lines = ["Не можу впевнено визначити вид. Найімовірніші варіанти:"]
        others = predictions
        header = None

    if others:
        if header:
            lines.append(header)
        lines.extend(f"  • {format_species(n)} — {p:.0%}" for n, p in others)

    tg.send_message(chat_id, "\n".join(lines))

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    update = await request.json()

    message = update.get("message") or update.get("edited_message") or {}
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not chat_id:
        return {"status": "ignored"}

    photo = message.get("photo")
    if photo:
        await run_in_threadpool(handle_photo, chat_id, photo)
        return {"status": "ok"}

    document = message.get("document") or {}
    if document.get("mime_type", "").startswith("image/"):
        await run_in_threadpool(
            handle_photo, chat_id, [{"file_id": document["file_id"]}]
        )
        return {"status": "ok"}

    text = (message.get("text") or "").strip()
    if not text:
        return {"status": "ignored"}

    if text == "/start":
        handle_start(chat_id)
    elif text == "/help":
        tg.send_message(chat_id, HELP_TEXT)
    elif text.startswith("/register"):
        handle_register(chat_id, text)
    elif text == "/status":
        handle_status(chat_id)
    else:
        tg.send_message(chat_id, "Невідома команда. Використайте /help")

    return {"status": "ok"}