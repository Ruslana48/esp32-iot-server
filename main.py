from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

last_data = {}

class SensorData(BaseModel):
    temperature: float
    humidity: float

@app.get("/")
def root():
    return {"message": "Server works"}

@app.post("/sensor-data")
def receive_data(data: SensorData):
    last_data["latest"] = {
        "temperature": data.temperature,
        "humidity": data.humidity
    }

    print(f"Received data: {last_data['latest']}", flush=True)

    return {
        "status": "ok",
        **last_data["latest"]
    }

@app.get("/latest")
def get_latest():
    return last_data