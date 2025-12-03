from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, login, logout
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.views import TokenRefreshView

from .models import User
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileSerializer
)

class UserRegistrationAPIView(APIView):
    """
    API endpoint for user registration.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Generate tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'status': 'success',
                'message': _('User registered successfully'),
                'user': UserProfileSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class UserLoginAPIView(APIView):
    """
    API endpoint for user login.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = authenticate(
                request,
                phone_number=serializer.validated_data['phone_number'],
                password=serializer.validated_data['password']
            )
            
            if user is not None and user.is_active:
                login(request, user)
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'status': 'success',
                    'message': _('Login successful'),
                    'user': UserProfileSerializer(user).data,
                    'tokens': {
                        'refresh': str(refresh),
                        'access': str(refresh.access_token),
                    }
                })
            
            return Response({
                'status': 'error',
                'message': _('Invalid credentials')
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class UserLogoutAPIView(APIView):
    """
    API endpoint for user logout.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            logout(request)
            return Response({
                'status': 'success',
                'message': _('Successfully logged out')
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': _('Error during logout')
            }, status=status.HTTP_400_BAD_REQUEST)


class UserProfileAPIView(APIView):
    """
    API endpoint to get or update user profile.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response({
            'status': 'success',
            'data': serializer.data
        })
    
    def put(self, request):
        serializer = UserProfileSerializer(
            request.user, 
            data=request.data, 
            partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'status': 'success',
                'message': _('Profile updated successfully'),
                'data': serializer.data
            })
        return Response({
            'status': 'error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class RefreshTokenView(TokenRefreshView):
    """
    API endpoint to refresh access token using refresh token.
    """
    pass
