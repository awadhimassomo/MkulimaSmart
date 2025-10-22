import os
import requests
import json
import sys
from datetime import datetime, timedelta

# Try to load .env file if dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed

# Get API key from environment variables
api_key = os.environ.get('OPENWEATHER_API_KEY')

if not api_key:
    print("Error: No API key found in environment variables")
    print("Make sure your .env file contains OPENWEATHER_API_KEY=your_key_here")
    exit(1)

print(f"Testing OpenWeatherMap API with key: {api_key[:5]}...{api_key[-5:]} (redacted middle)")

# Test coordinates (Dar es Salaam, Tanzania)
lat = -6.776
lon = 39.178

# Check if we should use timemachine endpoint
use_historical = len(sys.argv) > 1 and sys.argv[1] == '--historical'

# Parameters for the API request - using OneCall API 3.0
params = {
    'lat': lat,
    'lon': lon,
    'units': 'metric',  # For temperature in Celsius
    'appid': api_key
}

if use_historical:
    # Calculate timestamp for yesterday
    yesterday = datetime.now() - timedelta(days=1)
    timestamp = int(yesterday.timestamp())
    params['dt'] = timestamp
    
    # OneCall API 3.0 timemachine endpoint
    api_url = 'https://api.openweathermap.org/data/3.0/onecall/timemachine'
    print(f"Testing historical weather data for {yesterday.strftime('%Y-%m-%d')}")
else:
    params['exclude'] = 'minutely'  # Exclude minutely data
    # OneCall API 3.0 endpoint
    api_url = 'https://api.openweathermap.org/data/3.0/onecall'

try:
    print(f"Fetching weather data for lat={lat}, lon={lon}...")
    response = requests.get(api_url, params=params)
    response.raise_for_status()  # Raise exception for 4XX/5XX responses
    
    data = response.json()
    
    # Print out weather data based on endpoint used
    if use_historical:
        # Historical data has a different format
        data_type = "HISTORICAL WEATHER"
        current = data.get('data', [{}])[0] if data.get('data') else {}
    else:
        data_type = "CURRENT WEATHER"
        current = data.get('current', {})
    
    print(f"\n{data_type}:")
    print(f"Temperature: {current.get('temp')}°C")
    print(f"Humidity: {current.get('humidity')}%")
    print(f"Weather: {current.get('weather', [{}])[0].get('main', 'Unknown')} - {current.get('weather', [{}])[0].get('description', 'Unknown')}")
    if 'rain' in current:
        print(f"Rain (last 1h): {current.get('rain', {}).get('1h', 0)} mm")
    
    # Only show forecast if not using historical endpoint
    if not use_historical and 'daily' in data:
        # Print out daily forecast data
        print("\nDAILY FORECAST:")
        for day in data.get('daily', [])[:3]:  # First 3 days
            date = day.get('dt')
            date_str = datetime.fromtimestamp(date).strftime('%Y-%m-%d')
            print(f"\nDate: {date_str}")
            print(f"Temp (day): {day.get('temp', {}).get('day')}°C")
            if 'rain' in day:
                print(f"Rain: {day.get('rain')} mm")
            else:
                print("Rain: 0 mm")
            print(f"Weather: {day.get('weather', [{}])[0].get('main', 'Unknown')} - {day.get('weather', [{}])[0].get('description', 'Unknown')}")
    
    print("\nAPI TEST SUCCESSFUL!")
    
except requests.exceptions.RequestException as e:
    print(f"Error fetching weather data: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")