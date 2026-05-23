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
    device_id: str
    temperature: float = Field(..., ge=-40, le=80)
    humidity: float = Field(..., ge=0, le=100)

def send_telegram_message(chat_id: str, text: str):
    if not BOT_TOKEN:
        print("BOT_TOKEN is not set", flush=True)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})


@app.get("/")
def root():
    return {"message": "ESP32 IoT server works"}


@app.post("/sensor-data")
def receive_data(data: SensorData):
    latest_data[data.device_id] = {
        "temperature": data.temperature,
        "humidity": data.humidity,
        "timestamp": datetime.now()
    }

    chat_id = device_chat_map.get(data.device_id)

    temp_diff = abs(data.temperature - CONTROL_TEMP)
    hum_diff = abs(data.humidity - CONTROL_HUMIDITY)

    alert_sent = False

    if chat_id and (temp_diff > TEMP_ALLOWED_DIFF or hum_diff > HUMIDITY_ALLOWED_DIFF):
        send_telegram_message(
            chat_id,
            f"Alert from device {data.device_id}\n"
            f"Temperature: {data.temperature}°C\n"
            f"Humidity: {data.humidity}%\n"
            f"Temperature deviation: {temp_diff:.1f}°C\n"
            f"Humidity deviation: {hum_diff:.1f}%"
        )
        alert_sent = True

    print(f"Received data from {data.device_id}: {data.temperature}°C, {data.humidity}%", flush=True)

    return {
        "status": "ok",
        "device_id": data.device_id,
        "temperature": data.temperature,
        "humidity": data.humidity,
        "alert_sent": alert_sent
    }

@app.get("/latest/{device_id}")
def get_latest(device_id: str):
    if device_id not in latest_data:
        return {
            "device_id": device_id,
            "temperature": 0,
            "humidity": 0,
            "status": "no data"
        }

    data = latest_data[device_id]

    if datetime.now() - data["timestamp"] > timedelta(minutes=5):
        return {
            "device_id": device_id,
            "temperature": 0,
            "humidity": 0,
            "status": "device offline"
        }

    return {
        "device_id": device_id,
        "temperature": data["temperature"],
        "humidity": data["humidity"],
        "status": "online"
    }

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    update = await request.json()

    message = update.get("message", {})
    text = message.get("text", "").strip()
    chat = message.get("chat", {})
    chat_id = str(chat.get("id"))

    if not chat_id or not text:
        return {"status": "ignored"}

    if text == "/start":
        send_telegram_message(
            chat_id,
            "Hello! I am your ESP32 monitoring bot.\n\n"
            "Commands:\n"
            "/register esp32_001 - register your device\n"
            "/status - get latest sensor data\n"
            "/help - show commands"
        )
        return {"status": "ok"}

    if text == "/help":
        send_telegram_message(
            chat_id,
            "Available commands:\n"
            "/register esp32_001\n"
            "/status\n"
            "/help"
        )
        return {"status": "ok"}

    if text.startswith("/register"):
        parts = text.split()

        if len(parts) != 2:
            send_telegram_message(chat_id, "Use command like this:\n/register esp32_001")
            return {"status": "ok"}

        device_id = parts[1]
        device_chat_map[device_id] = chat_id

        send_telegram_message(chat_id, f"Device {device_id} registered successfully.")
        return {"status": "ok"}

    if text == "/status":
        user_devices = [
            device_id for device_id, saved_chat_id in device_chat_map.items()
            if saved_chat_id == chat_id
        ]

        if not user_devices:
            send_telegram_message(chat_id, "No device registered. Use:\n/register esp32_001")
            return {"status": "ok"}

        device_id = user_devices[0]
        data = latest_data.get(device_id)

        if not data:
            send_telegram_message(chat_id, f"No data received from {device_id} yet.")
            return {"status": "ok"}

        if datetime.now() - data["timestamp"] > timedelta(minutes=5):
            send_telegram_message(chat_id, f"Device {device_id} is offline.")
            return {"status": "ok"}

        send_telegram_message(
            chat_id,
            f"Device: {device_id}\n"
            f"Temperature: {data['temperature']}°C\n"
            f"Humidity: {data['humidity']}%\n"
            f"Status: online"
        )
        return {"status": "ok"}

    send_telegram_message(chat_id, "Unknown command. Use /help")
    return {"status": "ok"}