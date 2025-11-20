from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.conf import settings
from website.models import User  # Import User from website app
import jwt
from datetime import datetime, timedelta


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def obtain_token(request):
    """
    Endpoint to obtain JWT token for mobile apps to use with WebSocket connections
    
    Required fields (accepts both snake_case and camelCase):
    - phone_number/phoneNumber: The user's phone number
    - password: The user's password
    
    Optional:
    - thread_id/threadId: If connecting to a specific thread
    """
    # Handle both snake_case and camelCase
    data = {}
    for key, value in request.data.items():
        if key == 'phoneNumber':
            data['phone_number'] = value
        elif key == 'threadId':
            data['thread_id'] = value
        else:
            data[key] = value
    
    phone_number = data.get('phone_number')
    password = data.get('password')
    thread_id = data.get('thread_id')
    
    if not phone_number:
        return Response(
            {
                'error': 'Missing required field',
                'missing_field': 'phone_number',
                'note': 'Field can be either phone_number or phoneNumber',
                'received_data': dict(request.data)
            },
            status=status.HTTP_400_BAD_REQUEST
        )
        
    if not password:
        return Response(
            {'error': 'Password is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Authenticate user
    user = authenticate(request, phone_number=phone_number, password=password)
    
    if not user:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Create the JWT payload with extended expiration for WebSocket
    # Using 24 hours for WebSocket connections to prevent frequent disconnections
    expiration_hours = 24
    payload = {
        'uid': user.id,
        'phone_number': user.phone_number,
        'exp': datetime.utcnow() + timedelta(hours=expiration_hours),
    }
    
    # Include thread_id if provided
    if thread_id:
        payload['thread_id'] = thread_id
    
    # Create the token
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
    
    return Response({
        'token': token,
        'user_id': user.id,
        'expires_at': (datetime.utcnow() + timedelta(hours=expiration_hours)).isoformat(),
        'expires_in_hours': expiration_hours
    })
