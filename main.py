from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class SensorData(BaseModel):
    temperature: float
    humidity: float

@app.get("/")
def root():
    return {"message": "Server works"}

@app.post("/sensor-data")
def receive_data(data: SensorData):
    print(data)

    return {
        "status": "ok",
        "temperature": data.temperature,
        "humidity": data.humidity
    }