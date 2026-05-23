from fastapi import FastAPI
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import requests

app = FastAPI()

BOT_TOKEN = "8439826518:AAFOJ0mrF08mrJ8GL0om0Cl5IbkshwPr_7M"

CONTROL_TEMP = 24.0
CONTROL_HUMIDITY = 50.0

TEMP_ALLOWED_DIFF = 5.0
HUMIDITY_ALLOWED_DIFF = 15.0

last_data = {}

class SensorData(BaseModel):
    temperature: float = Field(..., ge=-40, le=80)
    humidity: float = Field(..., ge=0, le=100)

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, json=payload)

@app.post("/sensor-data")
def receive_data(data: SensorData):
    temp_diff = abs(data.temperature - CONTROL_TEMP)
    humidity_diff = abs(data.humidity - CONTROL_HUMIDITY)

    alert_sent = False

    if temp_diff > TEMP_ALLOWED_DIFF or humidity_diff > HUMIDITY_ALLOWED_DIFF:
        message = (
            "Sensor anomaly detected!\n"
            f"Temperature: {data.temperature}°C\n"
            f"Humidity: {data.humidity}%\n"
            f"Temperature difference: {temp_diff}°C\n"
            f"Humidity difference: {humidity_diff}%"
        )

        send_telegram_message(message)
        alert_sent = True

    return {
        "status": "ok",
        "temperature": data.temperature,
        "humidity": data.humidity,
        "alert_sent": alert_sent
    }

@app.get("/latest")
def get_latest():

    if "latest" not in last_data:
        return {
            "temperature": 0,
            "humidity": 0,
            "status": "no data"
        }

    now = datetime.now()

    last_timestamp = last_data["latest"]["timestamp"]

    if now - last_timestamp > timedelta(minutes=5):
        return {
            "temperature": 0,
            "humidity": 0,
            "status": "device offline"
        }

    return {
        "temperature": last_data["latest"]["temperature"],
        "humidity": last_data["latest"]["humidity"],
        "status": "online"
    }