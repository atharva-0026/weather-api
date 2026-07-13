from fastapi import FastAPI, HTTPException, Request, Query
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx, redis, json, os, asyncio, logging
from dotenv import load_dotenv
from datetime import datetime

from ml_forecast import get_or_train_model, predict_next_days

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5"

logging.basicConfig(filename="requests.log", level=logging.INFO, format="%(asctime)s %(message)s")

start_time = datetime.utcnow()
app = FastAPI(title="Weather API", description="Production-grade weather API with Redis caching, rate limiting, query history, and leaderboard.", version="3.0.0")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

r = redis.from_url(os.getenv("REDIS_URL", f"redis://{os.getenv('REDIS_HOST', 'localhost')}:6379/0"), decode_responses=True)

async def fetch(url, params):
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params={**params, "appid": API_KEY})
        data = res.json()
        if data.get("cod") not in [200, "200"]:
            raise HTTPException(status_code=404, detail=data.get("message", "City not found"))
        return data

def cache_get(key):
    val = r.get(key)
    return json.loads(val) if val else None

def cache_set(key, val, ttl=300):
    r.setex(key, ttl, json.dumps(val))

def log_query(city, endpoint):
    r.lpush(f"history:{city}", datetime.utcnow().isoformat())
    r.ltrim(f"history:{city}", 0, 49)
    r.zincrby("leaderboard", 1, city)
    logging.info(f"{endpoint} {city}")

async def refresh_cache():
    while True:
        await asyncio.sleep(1800)
        cities = r.zrevrange("leaderboard", 0, 9)
        for city in cities:
            try:
                data = await fetch(f"{BASE_URL}/weather", {"q": city, "units": "metric"})
                cache_set(f"weather:{city}:metric", data)
            except:
                pass

@app.on_event("startup")
async def startup():
    asyncio.create_task(refresh_cache())

@app.get("/health", summary="Health check")
async def health():
    uptime = str(datetime.utcnow() - start_time).split(".")[0]
    return {"status": "ok", "uptime": uptime, "redis": "connected" if r.ping() else "disconnected"}

@app.get("/version", summary="API version")
async def version():
    return {"version": "3.0.0", "service": "weather-api"}

@app.get("/weather/{city}", summary="Current weather")
@limiter.limit("10/minute")
async def get_weather(city: str, request: Request, units: str = Query("metric", enum=["metric", "imperial"])):
    key = f"weather:{city}:{units}"
    cached = cache_get(key)
    if cached:
        return {**cached, "source": "cache"}
    data = await fetch(f"{BASE_URL}/weather", {"q": city, "units": units})
    cache_set(key, data)
    log_query(city, "/weather")
    return {**data, "source": "api"}

@app.get("/weather/{city}/forecast", summary="5-day forecast")
@limiter.limit("10/minute")
async def get_forecast(city: str, request: Request, units: str = Query("metric", enum=["metric", "imperial"])):
    key = f"forecast:{city}:{units}"
    cached = cache_get(key)
    if cached:
        return {**cached, "source": "cache"}
    data = await fetch(f"{BASE_URL}/forecast", {"q": city, "units": units})
    cache_set(key, data)
    log_query(city, "/forecast")
    return {**data, "source": "api"}

@app.get("/weather/{city}/alerts", summary="Severe weather alerts")
@limiter.limit("10/minute")
async def get_alerts(city: str, request: Request):
    weather = await fetch(f"{BASE_URL}/weather", {"q": city, "units": "metric"})
    lat, lon = weather["coord"]["lat"], weather["coord"]["lon"]
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{BASE_URL}/onecall", params={"lat": lat, "lon": lon, "appid": API_KEY, "exclude": "current,minutely,hourly,daily"})
        data = res.json()
    return {"city": city, "alerts": data.get("alerts", "No active alerts")}

@app.get("/weather/{city}/uv", summary="UV index")
@limiter.limit("10/minute")
async def get_uv(city: str, request: Request):
    weather = await fetch(f"{BASE_URL}/weather", {"q": city, "units": "metric"})
    lat, lon = weather["coord"]["lat"], weather["coord"]["lon"]
    async with httpx.AsyncClient() as client:
        res = await client.get("https://api.openweathermap.org/data/2.5/uvi", params={"lat": lat, "lon": lon, "appid": API_KEY})
        data = res.json()
    log_query(city, "/uv")
    return {"city": city, "uv_index": data.get("value"), "lat": lat, "lon": lon}

@app.get("/weather/{city}/aqi", summary="Air quality index")
@limiter.limit("10/minute")
async def get_aqi(city: str, request: Request):
    key = f"aqi:{city}"
    cached = cache_get(key)
    if cached:
        return {**cached, "source": "cache"}
    weather = await fetch(f"{BASE_URL}/weather", {"q": city, "units": "metric"})
    lat, lon = weather["coord"]["lat"], weather["coord"]["lon"]
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{BASE_URL}/air_pollution", params={"lat": lat, "lon": lon, "appid": API_KEY})
        data = res.json()
    aqi = data.get("list", [{}])[0].get("main", {}).get("aqi")
    components = data.get("list", [{}])[0].get("components", {})
    result = {"city": city, "aqi": aqi, "components": components, "lat": lat, "lon": lon}
    cache_set(key, result, ttl=1800)
    log_query(city, "/aqi")
    return {**result, "source": "api"}

@app.get("/weather/{city}/ml-forecast", summary="ML-based temperature forecast")
@limiter.limit("5/minute")
async def ml_forecast(city: str, request: Request, days: int = Query(5, ge=1, le=14)):
    weather = await fetch(f"{BASE_URL}/weather", {"q": city, "units": "metric"})
    lat, lon = weather["coord"]["lat"], weather["coord"]["lon"]
    try:
        model, last_date = await get_or_train_model(city, lat, lon)
    except Exception:
        raise HTTPException(status_code=502, detail="Could not train forecast model, try again later")
    predictions = predict_next_days(model, last_date, days)
    log_query(city, "/ml-forecast")
    return {"city": city, "model": "RandomForestRegressor", "trained_through": last_date.isoformat(), "predictions": predictions}

@app.get("/compare", summary="Compare two cities")
@limiter.limit("10/minute")
async def compare(city1: str, city2: str, request: Request, units: str = Query("metric", enum=["metric", "imperial"])):
    w1 = await fetch(f"{BASE_URL}/weather", {"q": city1, "units": units})
    w2 = await fetch(f"{BASE_URL}/weather", {"q": city2, "units": units})
    unit_label = "°C" if units == "metric" else "°F"
    return {
        city1: {"temp": f"{w1['main']['temp']}{unit_label}", "humidity": w1["main"]["humidity"], "weather": w1["weather"][0]["description"]},
        city2: {"temp": f"{w2['main']['temp']}{unit_label}", "humidity": w2["main"]["humidity"], "weather": w2["weather"][0]["description"]},
    }

@app.get("/history/{city}", summary="Query history")
async def get_history(city: str):
    history = r.lrange(f"history:{city}", 0, -1)
    if not history:
        raise HTTPException(status_code=404, detail="No history found")
    return {"city": city, "queries": history}

@app.get("/top", summary="Most searched cities")
async def leaderboard():
    top = r.zrevrange("leaderboard", 0, 9, withscores=True)
    return {"leaderboard": [{"city": c, "searches": int(s)} for c, s in top]}

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/ui")
async def ui():
    return FileResponse("static/index.html")
