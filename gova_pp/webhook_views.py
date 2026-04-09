"""
Webhook endpoints for receiving chat messages from external systems
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import FarmerMessage, GovernmentReply
from website.models import User
import logging
import hashlib
import hmac

logger = logging.getLogger('gova_pp')


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def chat_webhook(request):
    """
    Webhook endpoint for receiving chat messages from external systems
    
    Accepts incoming messages and creates them in the system.
    Can be used by Kikapu or other external platforms.
    
    Expected payload:
    {
        "phone_number": "+255742178726",
        "message": "I need help with my crops",
        "subject": "Farming advice needed",
        "sender_name": "John Doe",
        "location": "Arusha, Tanzania",
        "priority": "medium",
        "message_type": "inquiry",
        "image_url": "https://example.com/image.jpg",
        "external_id": "kikapu_msg_123",
        "timestamp": "2025-10-21T16:30:00Z"
    }
    """
    
    # Log the incoming request
    logger.info(f"Webhook received from {request.META.get('REMOTE_ADDR')}")
    logger.debug(f"Webhook payload: {request.data}")
    
    try:
        # Extract data from payload - support multiple formats
        phone_number = request.data.get('phone_number')
        message_text = request.data.get('message') or request.data.get('content')  # Support 'content' from Flutter
        subject = request.data.get('subject')
        sender_name = request.data.get('sender_name', '')
        location = request.data.get('location', '')
        priority = request.data.get('priority', 'medium')
        message_type = request.data.get('message_type', 'inquiry')
        image_url = request.data.get('image_url', '')
        external_id = request.data.get('external_id') or request.data.get('conversation_id', '')  # Support conversation_id
        
        # Try to get thread_id if this is a reply to existing thread
        thread_id = request.data.get('thread_id') or request.data.get('conversation_id')
        
        # If thread_id is provided, this is a reply to existing thread
        if thread_id:
            try:
                thread = FarmerMessage.objects.get(id=thread_id)
                
                # Get or create system user for webhook replies
                system_user, created = User.objects.get_or_create(
                    phone_number='system_webhook',
                    defaults={
                        'first_name': 'System',
                        'last_name': 'Webhook',
                        'is_staff': True,
                        'is_active': True
                    }
                )
                
                # Add reply to existing thread
                reply = GovernmentReply.objects.create(
                    message=thread,
                    replied_by=system_user,
                    reply_text=message_text,
                    reply_type='answer'
                )
                
                thread.status = 'in_progress'
                thread.updated_at = timezone.now()
                thread.save()
                
                logger.info(f"Reply added to thread {thread_id} via webhook")
                
                return Response(
                    {
                        'status': 'success',
                        'message': 'Reply added to existing thread',
                        'thread_id': thread.id,
                        'reply_id': reply.id
                    },
                    status=status.HTTP_201_CREATED
                )
            except FarmerMessage.DoesNotExist:
                logger.warning(f"Thread {thread_id} not found, creating new thread")
                # Continue to create new thread below
        
        # Get phone number from user context or request
        if not phone_number:
            # Try to get from authenticated user if available
            if hasattr(request, 'user') and request.user.is_authenticated:
                phone_number = request.user.phone_number
                if not sender_name:
                    sender_name = request.user.get_full_name()
        
        # Validate required fields for new thread
        if not message_text:
            logger.warning("Webhook missing message content")
            return Response(
                {
                    'status': 'error',
                    'message': 'Missing required field: message or content is required'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If still no phone number, use a placeholder for external systems
        if not phone_number:
            phone_number = 'external_system'
            logger.warning("No phone number provided, using placeholder")
        
        # Check if user exists
        try:
            user = User.objects.get(phone_number=phone_number)
            if not sender_name:
                sender_name = user.get_full_name()
        except User.DoesNotExist:
            # User doesn't exist in our system
            logger.warning(f"Webhook received for unknown user: {phone_number}")
            if not sender_name:
                sender_name = phone_number
        
        # Use subject from message if not provided
        if not subject:
            subject = message_text[:50] + "..." if len(message_text) > 50 else message_text
        
        # Check if message with same external_id already exists (prevent duplicates)
        if external_id:
            existing = FarmerMessage.objects.filter(
                farmer_phone=phone_number,
                message=message_text,
                created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
            ).first()
            
            if existing:
                logger.info(f"Duplicate message detected: {external_id}")
                return Response(
                    {
                        'status': 'duplicate',
                        'message': 'Message already exists',
                        'thread_id': existing.id
                    },
                    status=status.HTTP_200_OK
                )
        
        # Create the farmer message
        farmer_message = FarmerMessage.objects.create(
            farmer_name=sender_name,
            farmer_phone=phone_number,
            farmer_location=location,
            message_type=message_type,
            subject=subject,
            message=message_text,
            status='new',
            priority=priority,
            has_image=bool(image_url),
            image_url=image_url,
        )
        
        logger.info(f"Webhook message created: Thread ID {farmer_message.id} from {phone_number}")
        
        # Return success response
        return Response(
            {
                'status': 'success',
                'message': 'Chat message received successfully',
                'thread_id': farmer_message.id,
                'created_at': farmer_message.created_at.isoformat(),
                'webhook_url': f'/en/gova-pp/messages/{farmer_message.id}/'
            },
            status=status.HTTP_201_CREATED
        )
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}", exc_info=True)
        return Response(
            {
                'status': 'error',
                'message': f'Error processing webhook: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def chat_webhook_reply(request):
    """
    Webhook endpoint for receiving replies to existing chat threads
    
    Expected payload:
    {
        "thread_id": 123,
        "message": "Here is the advice you requested",
        "sender_phone": "+255700000000",
        "sender_name": "Dr. Mary",
        "reply_type": "answer"
    }
    """
    
    logger.info(f"Reply webhook received from {request.META.get('REMOTE_ADDR')}")
    logger.debug(f"Reply webhook payload: {request.data}")
    
    try:
        thread_id = request.data.get('thread_id')
        reply_text = request.data.get('message')
        sender_phone = request.data.get('sender_phone')
        sender_name = request.data.get('sender_name', 'External System')
        reply_type = request.data.get('reply_type', 'answer')
        
        # Validate required fields
        if not thread_id or not reply_text:
            return Response(
                {
                    'status': 'error',
                    'message': 'Missing required fields: thread_id and message are required'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the thread
        try:
            thread = FarmerMessage.objects.get(id=thread_id)
        except FarmerMessage.DoesNotExist:
            logger.warning(f"Thread {thread_id} not found")
            return Response(
                {
                    'status': 'error',
                    'message': f'Thread {thread_id} not found'
                },
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Find or create a user for the sender
        replied_by = None
        if sender_phone:
            try:
                replied_by = User.objects.get(phone_number=sender_phone)
            except User.DoesNotExist:
                # Could create a guest user here if needed
                logger.warning(f"Sender {sender_phone} not found in system")
        
        # Create the reply
        reply = GovernmentReply.objects.create(
            message=thread,
            replied_by=replied_by,
            reply_text=reply_text,
            reply_type=reply_type
        )
        
        # Update thread status
        if thread.status == 'new':
            thread.status = 'in_progress'
        thread.updated_at = timezone.now()
        thread.save()
        
        logger.info(f"Reply added to thread {thread_id}")
        
        return Response(
            {
                'status': 'success',
                'message': 'Reply added successfully',
                'reply_id': reply.id,
                'thread_id': thread.id
            },
            status=status.HTTP_201_CREATED
        )
        
    except Exception as e:
        logger.error(f"Reply webhook error: {str(e)}", exc_info=True)
        return Response(
            {
                'status': 'error',
                'message': f'Error processing reply: {str(e)}'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def webhook_test(request):
    """
    Test endpoint to verify webhook is accessible
    """
    return Response(
        {
            'status': 'ok',
            'message': 'Webhook endpoint is active',
            'endpoints': {
                'create_message': '/api/chat/webhook/',
                'add_reply': '/api/chat/webhook/reply/',
                'test': '/api/chat/webhook/test/'
            },
            'timestamp': timezone.now().isoformat()
        },
        status=status.HTTP_200_OK
    )
