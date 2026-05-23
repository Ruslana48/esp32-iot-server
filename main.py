from fastapi import FastAPI
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

app = FastAPI()

last_data = {}

class SensorData(BaseModel):
    temperature: float = Field(..., ge=-40, le=80)
    humidity: float = Field(..., ge=0, le=100)

@app.post("/sensor-data")
def receive_data(data: SensorData):

    last_data["latest"] = {
        "temperature": data.temperature,
        "humidity": data.humidity,
        "timestamp": datetime.now()
    }

    print(f"Received data: {last_data['latest']}", flush=True)

    return {
        "status": "ok"
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