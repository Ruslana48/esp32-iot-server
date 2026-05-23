from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import requests

app = FastAPI()

BOT_TOKEN = "8439826518:AAFOJ0mrF08mrJ8GL0om0Cl5IbkshwPr_7M"

CONTROL_TEMP = 24.0
CONTROL_HUMIDITY = 50.0

TEMP_ALLOWED_DIFF = 5.0
HUMIDITY_ALLOWED_DIFF = 15.0

latest_data = {}
device_chat_map = {}

class SensorData(BaseModel):
    temperature: float = Field(..., ge=-40, le=80)
    humidity: float = Field(..., ge=0, le=100)

def send_telegram_message(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    update = await request.json()

    message = update.get("message", {})
    text = message.get("text", "")
    chat = message.get("chat", {})
    chat_id = str(chat.get("id"))

    if text.startswith("/register"):
        parts = text.split()

        if len(parts) != 2:
            send_telegram_message(chat_id, "Use: /register esp32_001")
            return {"status": "ok"}

        device_id = parts[1]
        device_chat_map[device_id] = chat_id

        send_telegram_message(chat_id, f"Device {device_id} registered successfully.")
        return {"status": "ok"}

    if text == "/status":
        for device_id, saved_chat_id in device_chat_map.items():
            if saved_chat_id == chat_id:
                data = latest_data.get(device_id)

                if not data:
                    send_telegram_message(chat_id, "No data received from your device yet.")
                else:
                    send_telegram_message(
                        chat_id,
                        f"Device: {device_id}\n"
                        f"Temperature: {data['temperature']}°C\n"
                        f"Humidity: {data['humidity']}%"
                    )
                return {"status": "ok"}

        send_telegram_message(chat_id, "No device registered. Use: /register esp32_001")
        return {"status": "ok"}

    send_telegram_message(chat_id, "Available commands:\n/register esp32_001\n/status")
    return {"status": "ok"}

@app.post("/sensor-data")
def receive_data(data: SensorData):
    latest_data[data.device_id] = {
        "temperature": data.temperature,
        "humidity": data.humidity
    }

    chat_id = device_chat_map.get(data.device_id)

    if chat_id:
        if data.temperature > 30 or data.humidity > 80:
            send_telegram_message(
                chat_id,
                f"Alert from {data.device_id}!\n"
                f"Temperature: {data.temperature}°C\n"
                f"Humidity: {data.humidity}%"
            )

    return {
        "status": "ok",
        "device_id": data.device_id,
        "temperature": data.temperature,
        "humidity": data.humidity
    }

@app.get("/latest")
def get_latest():

    if "latest" not in latest_data:
        return {
            "temperature": 0,
            "humidity": 0,
            "status": "no data"
        }

    now = datetime.now()

    last_timestamp = latest_data["latest"]["timestamp"]

    if now - last_timestamp > timedelta(minutes=5):
        return {
            "temperature": 0,
            "humidity": 0,
            "status": "device offline"
        }

    return {
        "temperature": latest_data["latest"]["temperature"],
        "humidity": latest_data["latest"]["humidity"],
        "status": "online"
    }