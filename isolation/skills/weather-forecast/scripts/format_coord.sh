#!/bin/bash
# Usage: ./format_coords.sh "Tokyo"

if [ -z "$1" ]; then
    echo "Error: Please provide a city name." >&2
    exit 1
fi

# Convert input to lowercase to match JSON keys
CITY=$(echo "$1" | tr '[:upper:]' '[:lower:]')
CACHE_FILE="../references/supported_cities.json"

# Extract latitude and longitude using jq
COORDS=$(jq -r ".[\"$CITY\"] | \"\(.lat) \(.lon)\"" "$CACHE_FILE")

if [ "$COORDS" = "null null" ]; then
    echo "Error: City '$1' not found in cache." >&2
    exit 1
fi

echo "$COORDS"