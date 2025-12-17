from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from django.conf import settings
import jwt
import requests
from datetime import datetime, timedelta
import json

from .models import Farm, Crop, Product, Category, User
from gova_pp.models import FarmerMessage, GovernmentReply

# Farm API Views
class FarmListCreateAPIView(generics.ListCreateAPIView):
    """
    API view to retrieve list of farms or create new farm
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Farm.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class FarmDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update or delete a farm
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Farm.objects.filter(owner=self.request.user)


# Crop API Views
class CropListCreateAPIView(generics.ListCreateAPIView):
    """
    API view to retrieve list of crops or create new crop
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Crop.objects.filter(farm__owner=self.request.user)
    
    def perform_create(self, serializer):
        farm_id = self.request.data.get('farm')
        farm = Farm.objects.get(id=farm_id, owner=self.request.user)
        serializer.save(farm=farm)


class CropDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update or delete a crop
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Crop.objects.filter(farm__owner=self.request.user)


# Product API Views
class ProductListAPIView(generics.ListAPIView):
    """
    API view to retrieve list of products
    """
    queryset = Product.objects.filter(is_active=True)


# Category API Views
class CategoryListAPIView(generics.ListAPIView):
    """
    API view to retrieve list of categories
    """
    queryset = Category.objects.filter(is_active=True)


def get_farmer_advice(weather_data):
    """Generate farming advice based on weather conditions."""
    advice = []

    temp = weather_data.get('temp') or weather_data.get('main', {}).get('temp', 25)
    rain = weather_data.get('rain', 0)
    wind_speed = weather_data.get('wind_speed') or weather_data.get('wind', {}).get('speed', 0)

    # Rain advice
    if rain > 5:
        advice.append({'priority': 'high', 'message': 'Heavy rain expected - ensure proper drainage.', 'icon': 'rain'})
    elif rain > 0:
        advice.append({'priority': 'medium', 'message': 'Light rain expected - good time for planting or irrigating.', 'icon': 'rain'})

    # Temperature advice
    if temp > 35:
        advice.append({'priority': 'high', 'message': 'Extreme heat expected - water crops early or late.', 'icon': 'hot'})
    elif temp > 30:
        advice.append({'priority': 'medium', 'message': 'Hot weather expected - ensure adequate irrigation.', 'icon': 'hot'})
    elif temp < 10:
        advice.append({'priority': 'high', 'message': 'Cold weather expected - protect sensitive crops.', 'icon': 'cold'})

    # Wind advice
    if wind_speed > 10:
        advice.append({'priority': 'medium', 'message': 'Strong winds expected - secure temporary structures.', 'icon': 'wind'})

    if not advice:
        advice.append({'priority': 'low', 'message': 'Weather conditions are favorable.', 'icon': 'good'})

    return advice


def format_weather_forecast_message(forecast_data):
    """Format weather forecast data into a user-friendly text message."""
    formatted_lines = []
    
    # Add each daily forecast
    for day in forecast_data:
        formatted_lines.append(f"=== Forecast for {day['date']} ===")
        formatted_lines.append(
            f"Temp: {day['temp']['day']:.2f}°C, "
            f"Rain: {day['rain']}mm, "
            f"Wind: {day['wind_speed']} m/s"
        )
        formatted_lines.append("Advice:")
        for advice in day['advice']:
            formatted_lines.append(f"- [{advice['priority']}] {advice['message']}")
        formatted_lines.append("=== End ===\n")
    
    return "\n".join(formatted_lines)


def generate_farming_timetable(forecast_data):
    """Generate a 5-day farming timetable based on weather forecast."""
    timetable = []
    
    for i, day in enumerate(forecast_data[:5], 1):  # Only use first 5 days
        date = day['date']
        temp = day['temp']['day']
        rain = day['rain']
        wind_speed = day['wind_speed']
        
        # Initialize daily plan
        daily_plan = {
            'day': i,
            'date': date,
            'weather_summary': f"Temp: {temp:.1f}°C, Rain: {rain}mm, Wind: {wind_speed} m/s",
            'morning_tasks': [],
            'afternoon_tasks': [],
            'evening_tasks': [],
            'priority': 'normal'
        }
        
        # Determine tasks based on weather
        if rain > 5:
            daily_plan['priority'] = 'high'
            daily_plan['morning_tasks'].append('Check drainage systems')
            daily_plan['morning_tasks'].append('Move potted plants to shelter')
            daily_plan['afternoon_tasks'].append('Inspect crops for waterlogging')
            daily_plan['evening_tasks'].append('Clear water from low areas')
        elif rain > 0:
            daily_plan['morning_tasks'].append('Prepare planting areas')
            daily_plan['afternoon_tasks'].append('Plant seeds/seedlings (good moisture)')
            daily_plan['evening_tasks'].append('Light weeding if soil is soft')
        else:
            daily_plan['morning_tasks'].append('Water crops (early morning)')
            daily_plan['afternoon_tasks'].append('Avoid watering during peak heat')
            daily_plan['evening_tasks'].append('Evening irrigation if needed')
        
        # Temperature-based tasks
        if temp > 35:
            daily_plan['priority'] = 'high'
            daily_plan['morning_tasks'].insert(0, 'Water crops before 7 AM')
            daily_plan['afternoon_tasks'].insert(0, 'Check for heat stress on plants')
            daily_plan['evening_tasks'].insert(0, 'Water again after 6 PM')
        elif temp > 30:
            daily_plan['morning_tasks'].append('Ensure adequate irrigation')
            daily_plan['afternoon_tasks'].append('Monitor soil moisture')
        elif temp < 15:
            daily_plan['morning_tasks'].append('Protect sensitive crops from cold')
        
        # Wind-based tasks
        if wind_speed > 10:
            daily_plan['morning_tasks'].insert(0, 'Secure structures and supports')
            daily_plan['afternoon_tasks'].append('Check stake supports for tall plants')
        
        # General farming tasks (not weather-dependent)
        if i == 1:  # First day
            daily_plan['morning_tasks'].append('Inspect all crops for pests/diseases')
        if i % 2 == 0:  # Every other day
            daily_plan['afternoon_tasks'].append('Weeding session')
        if i == 5:  # Last day
            daily_plan['evening_tasks'].append('Plan for next week')
        
        timetable.append(daily_plan)
    
    return timetable

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def weather_forecast(request):
    lat = request.query_params.get('lat')
    lon = request.query_params.get('lon')
    days_requested = int(request.query_params.get('days', 5))

    if not lat or not lon:
        return Response({'error': 'Latitude and longitude required'}, status=status.HTTP_400_BAD_REQUEST)

    api_key = getattr(settings, 'OPENWEATHER_API_KEY', '')
    if not api_key:
        return Response({'error': 'Weather service unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        base_url = "https://api.openweathermap.org/data/3.0/onecall"
        params = {
            'lat': lat,
            'lon': lon,
            'exclude': 'minutely,hourly,alerts',
            'appid': api_key,
            'units': 'metric'
        }
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        weather_data = response.json()

        data = {
            'location': 'Unknown',
            'coordinates': {'latitude': float(lat), 'longitude': float(lon)},
            'current_weather': {},
            'daily_forecast': [],
            'timestamp': datetime.utcnow().isoformat(),
            'unit': {'temperature': '°C', 'wind_speed': 'm/s', 'humidity': '%', 'rain': 'mm'}
        }

        # Current weather
        current = weather_data['current']
        data['current_weather'] = {
            'temperature': current['temp'],
            'feels_like': current['feels_like'],
            'humidity': current['humidity'],
            'wind_speed': current['wind_speed'],
            'condition': current['weather'][0]['description'],
            'icon': f"http://openweathermap.org/img/wn/{current['weather'][0]['icon']}@2x.png",
            'rain_1h': current.get('rain', {}).get('1h', 0)
        }
        data['current_weather']['advice'] = get_farmer_advice(current)

        # Daily forecast (skip current day)
        max_days = min(days_requested, len(weather_data['daily']) - 1)  # avoid index error
        for day in weather_data['daily'][1:max_days+1]:
            forecast = {
                'date': datetime.fromtimestamp(day['dt']).strftime('%Y-%m-%d'),
                'temp': {'min': day['temp']['min'], 'max': day['temp']['max'], 'day': day['temp']['day']},
                'humidity': day['humidity'],
                'wind_speed': day.get('wind_speed', 0),
                'condition': day['weather'][0]['description'],
                'icon': f"http://openweathermap.org/img/wn/{day['weather'][0]['icon']}@2x.png",
                'rain': day.get('rain', 0),
                'pop': day.get('pop', 0) * 100,
            }
            forecast['advice'] = get_farmer_advice({
                'temp': day['temp']['day'],
                'rain': day.get('rain', 0),
                'wind_speed': day.get('wind_speed', 0)
            })

            # Print daily forecast + advice to terminal
            print(f"\n=== Forecast for {forecast['date']} ===")
            print(f"Temp: {forecast['temp']['day']}°C, Rain: {forecast['rain']}mm, Wind: {forecast['wind_speed']} m/s")
            print("Advice:")
            for a in forecast['advice']:
                print(f"- [{a['priority']}] {a['message']}")
            print("=== End ===\n")

            data['daily_forecast'].append(forecast)

        # Add formatted message for easy display
        data['formatted_message'] = format_weather_forecast_message(data['daily_forecast'])

        return Response(data)

    except requests.exceptions.RequestException as e:
        return Response({'error': f'Error fetching weather data: {str(e)}'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def plan_farming_timetable(request):
    """
    Generate a 5-day farming timetable based on weather forecast.
    
    Query parameters:
    - lat: Latitude
    - lon: Longitude
    
    Returns:
    - 5-day timetable with morning, afternoon, and evening tasks
    - Tasks are based on weather conditions
    """
    lat = request.query_params.get('lat')
    lon = request.query_params.get('lon')
    
    if not lat or not lon:
        return Response(
            {'error': 'Latitude and longitude required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get 5-day weather forecast
    # Create a modified request for the weather_forecast function
    modified_request = request
    modified_request.query_params = modified_request.query_params.copy()
    modified_request.query_params['days'] = '5'
    
    try:
        # Get weather forecast
        forecast_response = weather_forecast(modified_request)
        
        if forecast_response.status_code != 200:
            return forecast_response
        
        forecast_data = forecast_response.data['daily_forecast']
        
        # Generate timetable
        timetable = generate_farming_timetable(forecast_data)
        
        # Format as a readable message
        formatted_message = "=== 5-Day Farming Timetable ===\n\n"
        
        for day_plan in timetable:
            formatted_message += f"📅 Day {day_plan['day']} - {day_plan['date']}\n"
            formatted_message += f"🌤️ Weather: {day_plan['weather_summary']}\n"
            if day_plan['priority'] == 'high':
                formatted_message += "⚠️ Priority: HIGH\n"
            formatted_message += "\n"
            
            if day_plan['morning_tasks']:
                formatted_message += "🌅 Morning Tasks:\n"
                for task in day_plan['morning_tasks']:
                    formatted_message += f"  • {task}\n"
            
            if day_plan['afternoon_tasks']:
                formatted_message += "☀️ Afternoon Tasks:\n"
                for task in day_plan['afternoon_tasks']:
                    formatted_message += f"  • {task}\n"
            
            if day_plan['evening_tasks']:
                formatted_message += "🌙 Evening Tasks:\n"
                for task in day_plan['evening_tasks']:
                    formatted_message += f"  • {task}\n"
            
            formatted_message += "\n" + "="*40 + "\n\n"
        
        formatted_message += "💡 Note: Adjust tasks based on your specific crops and farm conditions.\n"
        
        return Response({
            'status': 'success',
            'timetable': timetable,
            'formatted_message': formatted_message,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return Response(
            {'error': f'Error generating timetable: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def crop_prices(request):
    """
    API view to retrieve current crop prices
    """
    # This would integrate with a market price API or database
    # For now, return a placeholder response
    prices_data = [
        {'crop': 'Maize', 'price_per_kg': 45.50, 'market': 'Nairobi'},
        {'crop': 'Beans', 'price_per_kg': 120.75, 'market': 'Nairobi'},
        {'crop': 'Tomatoes', 'price_per_kg': 85.00, 'market': 'Nairobi'},
        {'crop': 'Potatoes', 'price_per_kg': 65.25, 'market': 'Nairobi'},
    ]
    return Response({
        'message': 'Crop prices retrieved successfully',
        'data': prices_data
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_farmer(request):
    """
    API endpoint to register a new farmer user
    
    Required fields (accepts both snake_case and camelCase):
    - phone_number/phoneNumber: The user's phone number
    - password: The user's password
    - first_name/firstName: The user's first name
    - last_name/lastName: The user's last name
    
    Optional fields:
    - email: The user's email address
    - farm_name: Name of the farm (optional)
    - farm_size_unit: Unit of farm size (e.g., acres, hectares)
    """
    # Print request data for debugging
    print("Request data:", request.data)
    
    # Check if request data is empty
    if not request.data:
        return Response(
            {'error': 'No data provided. Please provide the required fields in JSON format.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Handle both snake_case and camelCase field names
    data = {}
    for key, value in request.data.items():
        # Convert camelCase to snake_case
        if key == 'phoneNumber':
            data['phone_number'] = value
        elif key == 'firstName':
            data['first_name'] = value
        elif key == 'lastName':
            data['last_name'] = value
        elif key == 'farmName':
            data['farm_name'] = value
        elif key == 'farmSizeUnit':
            data['farm_size_unit'] = value
        else:
            data[key] = value
    
    # Check required fields
    required_fields = ['phone_number', 'password', 'first_name', 'last_name']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return Response(
            {
                'error': 'Missing required fields',
                'missing_fields': missing_fields,
                'received_data': dict(request.data),
                'required_fields': required_fields,
                'note': 'Field names are case-sensitive. Use snake_case or camelCase.'
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    phone_number = data['phone_number']
    
    # Check if user with this phone number already exists
    if User.objects.filter(phone_number=phone_number).exists():
        return Response(
            {'error': 'A user with this phone number already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            # Create the user with the processed data
            user = User.objects.create_user(
                phone_number=phone_number,
                password=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                email=data.get('email', ''),
                is_farmer=True  # Set as farmer
            )
            
            # Handle farm creation if farm data is provided
            if 'farm_name' in data:
                farm = Farm.objects.create(
                    name=data['farm_name'],
                    owner=user,
                    size=float(data.get('farm_size', 0)),
                    location=data.get('location', '')
                )
            
            # Create JWT token for immediate login (7 days expiration)
            expiration_days = 7
            payload = {
                'uid': user.id,
                'phone_number': user.phone_number,
                'exp': datetime.utcnow() + timedelta(days=expiration_days),
            }
            token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
            
            return Response({
                'message': 'Farmer registered successfully',
                'user_id': user.id,
                'token': token,
                'expires_at': (datetime.utcnow() + timedelta(days=expiration_days)).isoformat()
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        return Response(
            {'error': f'Error creating user: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Farmer Crops and Weather API Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_farmer_crops_weather(request):
    """
    API endpoint to get a farmer's crops and weather data for their farms
    
    Returns:
    - List of farms with their crops and current weather data
    """
    user = request.user
    
    # Verify the user is a farmer
    if not user.is_farmer:
        return Response(
            {'error': 'Only farmers can access this endpoint'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get all farms for the user
    farms = Farm.objects.filter(owner=user)
    
    response_data = []
    
    for farm in farms:
        # Get all crops for this farm
        crops = Crop.objects.filter(farm=farm)
        
        # Get weather data for the farm's location
        # Note: This assumes the farm model has latitude and longitude fields
        # If not, you'll need to modify this to get the location from somewhere else
        lat = getattr(farm, 'latitude', None)
        lon = getattr(farm, 'longitude', None)
        
        weather_data = None
        if lat is not None and lon is not None:
            try:
                # Use the existing weather_forecast function
                weather_response = weather_forecast(request._request)  # Pass the original request
                if weather_response.status_code == 200:
                    weather_data = weather_response.data
            except Exception as e:
                # Log the error but don't fail the whole request
                print(f"Error fetching weather data for farm {farm.id}: {str(e)}")
        
        # Prepare farm data with crops and weather
        farm_data = {
            'id': farm.id,
            'name': farm.name,
            'location': farm.location,
            'size': str(farm.size),
            'soil_type': farm.soil_type,
            'is_hydroponic': farm.is_hydroponic,
            'crops': [
                {
                    'id': crop.id,
                    'name': crop.name,
                    'planting_date': crop.planting_date.isoformat() if crop.planting_date else None,
                    'expected_harvest_date': crop.expected_harvest_date.isoformat() if crop.expected_harvest_date else None,
                    'quantity': str(crop.quantity),
                    'is_available_for_sale': crop.is_available_for_sale
                } for crop in crops
            ],
            'weather': weather_data
        }
        
        response_data.append(farm_data)
    
    return Response({
        'status': 'success',
        'data': response_data,
        'timestamp': datetime.utcnow().isoformat()
    })


# Chat API Views
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def chat_threads(request):
    """
    Get all chat threads (FarmerMessage) for the current user
    
    For farmers: Returns messages created by them
    For staff/agronomists: Returns messages assigned to them
    """
    user = request.user
    
    if user.is_farmer:
        # Farmers see messages they've created
        threads = FarmerMessage.objects.filter(
            farmer_phone=user.phone_number
        ).order_by('-updated_at')
    else:
        # Staff/agronomists see messages assigned to them
        threads = FarmerMessage.objects.filter(
            assigned_to=user
        ).order_by('-updated_at')
    
    result = []
    for thread in threads:
        # Get the last reply
        last_reply = GovernmentReply.objects.filter(
            message=thread
        ).order_by('-created_at').first()
        
        # Format the data
        thread_data = {
            'id': thread.id,
            'subject': thread.subject,
            'status': thread.status,
            'created_at': thread.created_at.isoformat(),
            'updated_at': thread.updated_at.isoformat(),
            'last_message': last_reply.reply_text if last_reply else thread.message,
            'last_message_time': (last_reply.created_at if last_reply else thread.created_at).isoformat(),
            'other_party_name': thread.farmer_name,
            'other_party_phone': thread.farmer_phone,
            'unread_count': 0,  # Future enhancement: track unread counts
            'has_image': thread.has_image,
        }
        result.append(thread_data)
    
    return Response(result)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def chat_thread_messages(request, thread_id):
    """
    Get all messages for a specific chat thread
    
    Includes the original farmer message and all government replies
    """
    user = request.user
    
    try:
        # Verify access permission
        if user.is_farmer:
            thread = FarmerMessage.objects.get(
                id=thread_id,
                farmer_phone=user.phone_number
            )
        else:
            thread = FarmerMessage.objects.get(
                id=thread_id,
                assigned_to=user
            )
    except FarmerMessage.DoesNotExist:
        return Response(
            {'error': 'Thread not found or you do not have permission to access it'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Get all replies for this thread
    replies = GovernmentReply.objects.filter(message=thread).order_by('created_at')
    
    # Format the original message
    messages = [{
        'id': f'original_{thread.id}',
        'text': thread.message,
        'sender': {
            'id': 'farmer',
            'name': thread.farmer_name,
            'phone': thread.farmer_phone,
            'is_farmer': True
        },
        'created_at': thread.created_at.isoformat(),
        'has_image': thread.has_image,
        'image_url': thread.image_url if thread.has_image and thread.image_url else None,
    }]
    
    # Add all the replies
    for reply in replies:
        messages.append({
            'id': str(reply.id),
            'text': reply.reply_text,
            'sender': {
                'id': reply.replied_by.id,
                'name': reply.replied_by.get_full_name(),
                'is_farmer': False
            },
            'created_at': reply.created_at.isoformat(),
            'reply_type': reply.reply_type,
        })
    
    return Response(messages)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_thread_message(request, thread_id):
    """
    Create a new message in a chat thread
    
    For farmers: Creates a new FarmerMessage reply (TODO: implement)
    For staff/agronomists: Creates a new GovernmentReply
    """
    user = request.user
    
    try:
        # Verify access permission and get the thread
        if user.is_farmer:
            thread = FarmerMessage.objects.get(
                id=thread_id,
                farmer_phone=user.phone_number
            )
            # TODO: Implement farmer replies as needed
            return Response(
                {'error': 'Farmer replies not yet implemented'},
                status=status.HTTP_501_NOT_IMPLEMENTED
            )
        else:
            thread = FarmerMessage.objects.get(
                id=thread_id,
                assigned_to=user
            )
    except FarmerMessage.DoesNotExist:
        return Response(
            {'error': 'Thread not found or you do not have permission to access it'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Create reply from agronomist/staff
    text = request.data.get('text')
    if not text:
        return Response(
            {'error': 'Message text is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    reply = GovernmentReply.objects.create(
        message=thread,
        replied_by=user,
        reply_text=text,
        reply_type=request.data.get('reply_type', 'answer')
    )
    
    # Update thread status if needed
    if thread.status == 'new':
        thread.status = 'in_progress'
        thread.save(update_fields=['status', 'updated_at'])
    
    # Format the response
    response_data = {
        'id': str(reply.id),
        'text': reply.reply_text,
        'sender': {
            'id': reply.replied_by.id,
            'name': reply.replied_by.get_full_name(),
            'is_farmer': False
        },
        'created_at': reply.created_at.isoformat(),
        'reply_type': reply.reply_type,
    }
    
    return Response(response_data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_chat_thread(request):
    """
    Create a new chat thread (farmer message)
    
    Only farmers can create new threads
    """
    user = request.user
    
    if not user.is_farmer:
        return Response(
            {'error': 'Only farmers can create new message threads'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Create new farmer message
    message_text = request.data.get('message')
    subject = request.data.get('subject')
    
    if not message_text or not subject:
        return Response(
            {'error': 'Message text and subject are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    thread = FarmerMessage.objects.create(
        farmer_name=user.get_full_name(),
        farmer_phone=user.phone_number,
        farmer_location=request.data.get('location', ''),
        message_type=request.data.get('message_type', 'inquiry'),
        subject=subject,
        message=message_text,
        status='new',
        priority=request.data.get('priority', 'medium'),
        has_image=bool(request.data.get('image_url', '')),
        image_url=request.data.get('image_url', ''),
    )
    
    # Format the response
    response_data = {
        'id': thread.id,
        'subject': thread.subject,
        'status': thread.status,
        'created_at': thread.created_at.isoformat(),
        'updated_at': thread.updated_at.isoformat(),
        'message': thread.message,
        'has_image': thread.has_image,
    }
    
    return Response(response_data, status=status.HTTP_201_CREATED)
