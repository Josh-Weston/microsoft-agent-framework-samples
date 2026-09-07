---
name: weather-forecast
description: Provides current weather conditions and forecasts for supported cities. Use when asked about the weather, forecasts, or extreme weather alerts.
license: Apache-2.0
compatibility: Requires python3
metadata:
  author: jweston
  version: "1.0"
---

# Weather Forecast

Use this skill when a user asks for current weather conditions, you must strictly follow the workflow below using the provided scripts, references, and templates. Do not hallucinate weather data; always execute the tools.

## Asset Inventory

### 1. Scripts (Execution)
*   **`scripts/format_coords.sh <city_name>`**: A bash script that converts a city name into latitude and longitude coordinates. 
    *   *Output:* A string in the format `<latitude> <longitude>` (e.g., `35.6895 139.6917`).
*   **`scripts/fetch_weather.py <latitude> <longitude>`**: A Python script that calls the Open-Meteo API.
    *   *Output:* A JSON object containing `temperature`, `windspeed`, `winddirection`, `weathercode`, and `time`.

### 2. References (Lookup)
*   **`references/supported_cities.json`**: The internal cache used by `format_coords.sh`. If the bash script fails, you may read this file directly to find coordinates.
*   **`references/wmo_weather_codes.csv`**: A CSV mapping the integer `weathercode` returned by the API to a human-readable condition (e.g., `61` = `Slight rain`).

### 3. Templates (Formatting)
*   **`template/daily_summary.jinja`**: The default markdown layout for standard weather conditions.
*   **`template/extreme_weather_alert.md`**: The layout required if the weather condition is severe.

---

## Execution Workflow

When triggered by a weather-related query, perform the following steps sequentially:

**Step 1: Resolve Coordinates**
Execute `scripts/format_coords.sh "<city_name>"`. 
*   *If successful:* Capture the `lat` and `lon`.
*   *If it returns an error (city not in cache):* Apologize to the user and state that the city is not in the supported database. Terminate the skill.

**Step 2: Fetch Weather Data**
Execute `scripts/fetch_weather.py <lat> <lon>` using the coordinates obtained in Step 1.
*   Parse the resulting JSON payload.

**Step 3: Decode the Weather Condition**
Read `references/wmo_weather_codes.csv`. Find the row where the `code` matches the `weathercode` from your JSON payload. 
*   Extract the corresponding `description` (e.g., `Clear sky`, `Thunderstorm`).

**Step 4: Select and Render the Template**
Evaluate the `weathercode` to choose the correct presentation template:
*   **Condition A (Extreme Weather):** If the `weathercode` is `90` or higher (e.g., thunderstorms, hail), read `template/extreme_weather_alert.md`.
*   **Condition B (Normal Weather):** For all other codes, read `template/daily_summary.jinja`.

Inject the variables (`city`, `weather_description`, `temp_c`, `wind_speed_kmh`, and `timestamp`) into the chosen template and output the final rendered text to the user. Do not include raw JSON or execution logs in the final response.