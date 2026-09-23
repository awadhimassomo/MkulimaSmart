"""
Weather utility functions for fetching weather data from OpenWeatherMap API
"""
import os
import requests
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


def get_coordinates_from_location(location_name):
    """
    Get latitude and longitude from a location name using OpenWeatherMap Geocoding API
    
    Args:
        location_name (str): Name of the location (e.g., "Dar es Salaam, Tanzania")
        
    Returns:
        tuple: (latitude, longitude) or (None, None) if not found
    """
    api_key = getattr(settings, 'OPENWEATHER_API_KEY', os.environ.get('OPENWEATHER_API_KEY'))
    
    if not api_key:
        logger.error("OpenWeatherMap API key not found")
        return None, None
    
    # Check cache first (cache for 7 days since coordinates don't change)
    cache_key = f'geocode_{location_name}'
    cached_coords = cache.get(cache_key)
    if cached_coords:
        return cached_coords
    
    try:
        # OpenWeatherMap Geocoding API
        geocoding_url = 'http://api.openweathermap.org/geo/1.0/direct'
        params = {
            'q': location_name,
            'limit': 1,
            'appid': api_key
        }
        
        response = requests.get(geocoding_url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data and len(data) > 0:
            lat = data[0].get('lat')
            lon = data[0].get('lon')
            
            # Cache the result
            cache.set(cache_key, (lat, lon), 60 * 60 * 24 * 7)  # 7 days
            
            return lat, lon
        else:
            logger.warning(f"No coordinates found for location: {location_name}")
            return None, None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching coordinates for {location_name}: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error in geocoding: {e}")
        return None, None


def get_weather_data(lat, lon):
    """
    Get current weather data from OpenWeatherMap API
    
    Args:
        lat (float): Latitude
        lon (float): Longitude
        
    Returns:
        dict: Weather data or None if error
    """
    api_key = getattr(settings, 'OPENWEATHER_API_KEY', os.environ.get('OPENWEATHER_API_KEY'))
    
    if not api_key:
        logger.error("OpenWeatherMap API key not found")
        return None
    
    # Check cache first (cache for 30 minutes)
    cache_key = f'weather_{lat}_{lon}'
    cached_weather = cache.get(cache_key)
    if cached_weather:
        return cached_weather
    
    try:
        # OpenWeatherMap OneCall API 3.0
        api_url = 'https://api.openweathermap.org/data/3.0/onecall'
        params = {
            'lat': lat,
            'lon': lon,
            'units': 'metric',  # Celsius
            'exclude': 'minutely,hourly',  # We only need current and daily
            'appid': api_key
        }
        
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract relevant weather information
        current = data.get('current', {})
        daily = data.get('daily', [])
        
        weather_info = {
            'temperature': current.get('temp'),
            'feels_like': current.get('feels_like'),
            'humidity': current.get('humidity'),
            'pressure': current.get('pressure'),
            'wind_speed': current.get('wind_speed'),
            'weather_main': current.get('weather', [{}])[0].get('main', 'Unknown'),
            'weather_description': current.get('weather', [{}])[0].get('description', 'Unknown'),
            'weather_icon': current.get('weather', [{}])[0].get('icon', '01d'),
            'uvi': current.get('uvi', 0),
            'clouds': current.get('clouds', 0),
            'daily_forecast': []
        }
        
        # Add daily forecast (next 3 days)
        for day in daily[:3]:
            weather_info['daily_forecast'].append({
                'date': day.get('dt'),
                'temp_min': day.get('temp', {}).get('min'),
                'temp_max': day.get('temp', {}).get('max'),
                'temp_day': day.get('temp', {}).get('day'),
                'humidity': day.get('humidity'),
                'weather_main': day.get('weather', [{}])[0].get('main', 'Unknown'),
                'weather_description': day.get('weather', [{}])[0].get('description', 'Unknown'),
                'weather_icon': day.get('weather', [{}])[0].get('icon', '01d'),
                'rain': day.get('rain', 0),
                'pop': day.get('pop', 0) * 100  # Probability of precipitation (as percentage)
            })
        
        # Cache the result for 30 minutes
        cache.set(cache_key, weather_info, 60 * 30)
        
        return weather_info
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather data for lat={lat}, lon={lon}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching weather: {e}")
        return None


def get_weather_for_location(location_name):
    """
    Get weather data for a location name (combines geocoding and weather fetching)
    
    Args:
        location_name (str): Name of the location
        
    Returns:
        dict: Weather data or None if error
    """
    lat, lon = get_coordinates_from_location(location_name)
    
    if lat is None or lon is None:
        logger.warning(f"Could not get coordinates for location: {location_name}")
        return None
    
    return get_weather_data(lat, lon)


def get_weather_icon_url(icon_code):
    """
    Get the full URL for a weather icon
    
    Args:
        icon_code (str): Icon code from OpenWeatherMap (e.g., '01d')
        
    Returns:
        str: Full URL to the icon image
    """
    return f"https://openweathermap.org/img/wn/{icon_code}@2x.png"
