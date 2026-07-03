from fastapi import FastAPI
import httpx

app = FastAPI()

API_KEY = "a60275aac80f1ac0be0a8d0d700c037c"
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

@app.get("/weather/{city}")
async def get_weather(city: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(BASE_URL, params={"q": city, "appid": API_KEY, "units": "metric"})
        return r.json()
