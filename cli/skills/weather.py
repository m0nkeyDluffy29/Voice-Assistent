"""
Weather + time skill.
Uses Open-Meteo (no API key needed, free forever).

Voice commands:
    "what's the weather"
    "weather in Mumbai"
    "what time is it"
    "time in New York"
    "what's today's date"
"""
import urllib.request
import urllib.parse
import json
from datetime import datetime
import re

WEATHER_TRIGGERS = ["weather", "temperature", "hot", "cold", "raining", "rain"]
TIME_TRIGGERS    = ["what time", "time in", "current time", "what's the time"]
DATE_TRIGGERS    = ["what date", "today's date", "what day", "date today"]

# Cache location coordinates (avoids re-geocoding on every query)
_geocode_cache = {}


def can_handle(query: str) -> bool:
    q = query.lower()
    return (any(t in q for t in WEATHER_TRIGGERS) or
            any(t in q for t in TIME_TRIGGERS) or
            any(t in q for t in DATE_TRIGGERS))


def handle(query: str, agent_name: str, language: str) -> str:
    q = query.lower()

    if any(t in q for t in DATE_TRIGGERS):
        return _date_response()

    if any(t in q for t in TIME_TRIGGERS):
        city = _extract_city(query, TIME_TRIGGERS)
        return _time_response(city)

    if any(t in q for t in WEATHER_TRIGGERS):
        city = _extract_city(query, WEATHER_TRIGGERS)
        return _weather_response(city)

    return None


def _extract_city(query: str, triggers: list) -> str:
    """Extract 'Mumbai' from 'what's the weather in Mumbai'."""
    q = query.lower()
    # Look for "in <city>" pattern
    m = re.search(r"\bin ([a-z][a-z\s]+?)(?:\?|$|\.|,)", q)
    if m:
        return m.group(1).strip().title()
    return None   # None = use user's current location


def _geocode(city: str) -> tuple:
    """City name → (lat, lon, display_name). Free Nominatim OSM API."""
    if city in _geocode_cache:
        return _geocode_cache[city]
    try:
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        if data.get("results"):
            res = data["results"][0]
            coords = (res["latitude"], res["longitude"], res["name"])
            _geocode_cache[city] = coords
            return coords
    except Exception:
        pass
    return None


def _weather_response(city: str = None) -> str:
    if city:
        geo = _geocode(city)
        if not geo:
            return f"I couldn't find {city}. Try another location."
        lat, lon, name = geo
    else:
        # No city given — use user's location (fallback: Ajmer from location config)
        lat, lon, name = 26.4499, 74.6399, "your location"

    try:
        url = (f"https://api.open-meteo.com/v1/forecast?"
               f"latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=celsius")
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        cw = data["current_weather"]
        temp = round(cw["temperature"])
        wind = round(cw["windspeed"])
        code = cw["weathercode"]
        condition = _weather_code_to_text(code)
        return f"It's {temp}° in {name}, {condition}, wind at {wind} km/h."
    except Exception as e:
        return f"Weather service is not responding. Try again later."


def _weather_code_to_text(code: int) -> str:
    """Open-Meteo WMO weather codes."""
    if code == 0:
        return "clear sky"
    if code in (1, 2, 3):
        return "mostly clear"
    if code in (45, 48):
        return "foggy"
    if code in (51, 53, 55, 56, 57):
        return "light drizzle"
    if code in (61, 63, 65, 66, 67):
        return "rainy"
    if code in (71, 73, 75, 77):
        return "snowing"
    if code in (80, 81, 82):
        return "rain showers"
    if code in (95, 96, 99):
        return "thunderstorms"
    return "cloudy"


def _time_response(city: str = None) -> str:
    if not city:
        now = datetime.now()
        return f"It's {now.strftime('%I:%M %p')}."

    # For city time, we need a timezone lookup
    try:
        import zoneinfo
        # Try common city → timezone mappings first
        tz_map = {
            "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
            "bangalore": "Asia/Kolkata", "chennai": "Asia/Kolkata", "kolkata": "Asia/Kolkata",
            "hyderabad": "Asia/Kolkata", "pune": "Asia/Kolkata",
            "new york": "America/New_York", "los angeles": "America/Los_Angeles",
            "chicago": "America/Chicago", "san francisco": "America/Los_Angeles",
            "london": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin",
            "tokyo": "Asia/Tokyo", "shanghai": "Asia/Shanghai", "beijing": "Asia/Shanghai",
            "dubai": "Asia/Dubai", "sydney": "Australia/Sydney", "singapore": "Asia/Singapore",
        }
        tz_name = tz_map.get(city.lower())
        if tz_name:
            tz = zoneinfo.ZoneInfo(tz_name)
            now = datetime.now(tz)
            return f"It's {now.strftime('%I:%M %p')} in {city}."
    except Exception:
        pass
    return f"I couldn't figure out the time zone for {city}."


def _date_response() -> str:
    now = datetime.now()
    return f"Today is {now.strftime('%A, %B %d, %Y')}."