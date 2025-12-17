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
    """Generate farming advice based on weather conditions"""
    advice = []
    
    # Check for rain conditions
    if 'rain' in weather_data and weather_data['rain'].get('1h', 0) > 5:  # More than 5mm rain in 1 hour
        advice.append({
            'priority': 'high',
            'message': 'Heavy rain expected - ensure proper drainage in your fields to prevent waterlogging.',
            'icon': 'rain'
        })
    elif 'rain' in weather_data and weather_data['rain'].get('1h', 0) > 0:
        advice.append({
            'priority': 'medium',
            'message': 'Light rain expected - good time for planting or irrigating.',
            'icon': 'rain'
        })
    
    # Check temperature conditions
    temp = weather_data['main']['temp']
    if temp > 35:  # Very hot
        advice.append({
            'priority': 'high',
            'message': 'Extreme heat expected - water crops in the early morning or late evening to reduce evaporation.',
            'icon': 'hot'
        })
    elif temp > 30:  # Hot
        advice.append({
            'priority': 'medium',
            'message': 'Hot weather expected - ensure adequate irrigation for your crops.',
            'icon': 'hot'
        })
    elif temp < 10:  # Cold
        advice.append({
            'priority': 'high',
            'message': 'Cold weather expected - protect sensitive crops from frost.',
            'icon': 'cold'
        })
    
    # Check wind conditions
    if 'wind' in weather_data and weather_data['wind'].get('speed', 0) > 10:  # Strong wind
        advice.append({
            'priority': 'medium',
            'message': 'Strong winds expected - secure any temporary structures and protect young plants.',
            'icon': 'wind'
        })
    
    # If no specific advice, provide general advice
    if not advice:
        advice.append({
            'priority': 'low',
            'message': 'Weather conditions are favorable for most farming activities.',
            'icon': 'good'
        })
    
    return advice

# Weather API Views
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def weather_forecast(request):
    """
    API view to retrieve weather forecast data from OpenWeather API
    
    Query Parameters:
    - lat: Latitude (required)
    - lon: Longitude (required)
    """
    # Get location parameters
    lat = request.query_params.get('lat')
    lon = request.query_params.get('lon')
    
    if not lat or not lon:
        return Response(
            {'error': 'Latitude and longitude are required parameters'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get OpenWeather API key from settings
    api_key = getattr(settings, 'OPENWEATHER_API_KEY', '')
    if not api_key:
        return Response(
            {'error': 'Weather service is currently unavailable'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    try:
        # Make API call to OpenWeather
        base_url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': api_key,
            'units': 'metric',  # Get temperature in Celsius
        }
        
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        weather_data = response.json()
        
        # Debug: Print the raw API response
        print("\n=== RAW OPENWEATHER API RESPONSE ===")
        print(json.dumps(weather_data, indent=2))
        print("=== END OF RAW RESPONSE ===\n")
        
        # Extract relevant weather information
        location_name = weather_data.get('name', 'Unknown Location')
        
        # Generate farmer advice based on weather conditions
        advice = get_farmer_advice(weather_data)
        
        # Prepare response data
        data = {
            'location': location_name,
            'coordinates': {
                'latitude': float(lat),
                'longitude': float(lon)
            },
            'current_weather': {
                'temperature': weather_data['main']['temp'],
                'feels_like': weather_data['main']['feels_like'],
                'humidity': weather_data['main']['humidity'],
                'wind_speed': weather_data['wind']['speed'],
                'condition': weather_data['weather'][0]['description'],
                'icon': f"http://openweathermap.org/img/wn/{weather_data['weather'][0]['icon']}@2x.png"
            },
            'advice': advice,
            'unit': {
                'temperature': '°C',
                'wind_speed': 'm/s',
                'humidity': '%',
                'coordinates': 'decimal degrees'
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Add rain data if available
        if 'rain' in weather_data:
            data['current_weather']['rain_1h'] = weather_data['rain'].get('1h', 0)
            data['unit']['rain'] = 'mm'
        
        return Response(data)
        
    except requests.exceptions.RequestException as e:
        return Response(
            {'error': f'Error fetching weather data: {str(e)}'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return Response(data)


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
