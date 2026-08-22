#!/usr/bin/env python3
import sys
import requests
import json


def get_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json().get('current_weather', {})
        return json.dumps(data)
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"API request failed: {str(e)}"})


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('{"error": "Usage: fetch_weather.py <latitude> <longitude>"}')
        sys.exit(1)

    latitude, longitude = sys.argv[1], sys.argv[2]
    print(get_weather(latitude, longitude))
