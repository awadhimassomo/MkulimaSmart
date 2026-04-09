import os
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
import logging

# Import models
from .models import FarmerMessage, GovernmentReply, ChatMedia

# Set up logging
logger = logging.getLogger('gova_pp')


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def chat_threads_endpoint(request):
    """
    Combined endpoint for chat threads
    
    GET: List all chat threads for the current user
    POST: Create a new chat thread (farmers only)
    """
    user = request.user
    
    if request.method == 'POST':
        # Log the incoming data for debugging
        print(f"DEBUG - POST data received: {request.data}")
        logger.debug(f"POST data received: {request.data}")
        
        # Create a new chat thread (code from create_chat_thread function)
        if not user.is_farmer:
            return Response(
                {'error': 'Only farmers can create new message threads'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create new farmer message
        message_text = request.data.get('message')
        subject = request.data.get('subject')
        content = request.data.get('content')  # Try alternative field name
        title = request.data.get('title')      # Try alternative field name
        
        # Log the extracted values
        print(f"DEBUG - Extracted fields: message={message_text}, subject={subject}, content={content}, title={title}")
        logger.debug(f"Extracted fields: message={message_text}, subject={subject}, content={content}, title={title}")
        
        # Use alternative field names if primary ones are empty
        if not message_text and content:
            message_text = content
            print(f"DEBUG - Using 'content' field for message: {message_text}")
            
        if not subject and title:
            subject = title
            print(f"DEBUG - Using 'title' field for subject: {subject}")
        
        # For testing: use default values if still empty
        if not message_text:
            message_text = "Default test message from Flutter app"
            print(f"DEBUG - Using default message: {message_text}")
            
        if not subject:
            subject = "Test Thread from Flutter"
            print(f"DEBUG - Using default subject: {subject}")
            
        # Disabled validation for testing
        # if not message_text or not subject:
        #     return Response(
        #         {'error': 'Message text and subject are required'},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )
        
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
        
    else:  # GET
        # Get all chat threads (code from get_chat_threads function)
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
                'other_party_name': thread.farmer_name if not user.is_farmer else "Agronomist",
                'other_party_phone': thread.farmer_phone if not user.is_farmer else "",
                'unread_count': 0,  # Future enhancement: track unread counts
                'has_image': thread.has_image,
            }
            result.append(thread_data)
        
        return Response(result)
        
        
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_chat_threads(request):
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
            'other_party_name': thread.farmer_name if not user.is_farmer else "Agronomist",
            'other_party_phone': thread.farmer_phone if not user.is_farmer else "",
            'unread_count': 0,  # Future enhancement: track unread counts
            'has_image': thread.has_image,
        }
        result.append(thread_data)
    
    return Response(result)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def chat_thread_messages(request, thread_id):
    """
    GET: Get all messages for a specific chat thread
    POST: Create a new message in the thread
    
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
    
    # Handle POST request - create a new message
    if request.method == 'POST':
        # Create reply based on user type
        if user.is_farmer:
            # Farmer is replying to their own thread
            text = request.data.get('text') or request.data.get('message')
            if not text:
                return Response(
                    {'error': 'Message text is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create a reply as a GovernmentReply entry (for conversation continuity)
            # Even though it's from a farmer, store it in GovernmentReply so all messages
            # in a thread are in one place
            reply = GovernmentReply.objects.create(
                message=thread,
                replied_by=user,
                reply_text=text,
                reply_type='farmer_reply'  # Mark it as a farmer reply
            )
            
            # Update thread status and timestamp
            if thread.status == 'resolved':
                thread.status = 'in_progress'  # Reopen if farmer replies to resolved thread
            thread.updated_at = timezone.now()
            thread.save(update_fields=['status', 'updated_at'])
            
            # Format the response
            response_data = {
                'id': str(reply.id),
                'text': reply.reply_text,
                'sender': {
                    'id': user.id,
                    'name': user.get_full_name(),
                    'phone': user.phone_number,
                    'is_farmer': True
                },
                'created_at': reply.created_at.isoformat(),
                'reply_type': reply.reply_type,
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)
        else:
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
            else:
                # Always update the updated_at field to show activity
                thread.updated_at = timezone.now()
                thread.save(update_fields=['updated_at'])
            
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
    
    # Handle GET request - get all messages
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
@permission_classes([IsAuthenticated])
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
            
            # Implement farmer replies with image support
            text = request.data.get('text') or request.data.get('message')
            if not text:
                return Response(
                    {'error': 'Message text is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Handle image if provided
            image_url = request.data.get('image_url', '')
            
            # Create a new farmer message as a reply
            reply_thread = FarmerMessage.objects.create(
                farmer_name=user.get_full_name(),
                farmer_phone=user.phone_number,
                farmer_location=request.data.get('location', thread.farmer_location),
                message_type=thread.message_type,  # Inherit the original thread type
                subject=f"RE: {thread.subject}",  # Mark as a reply
                message=text,
                status='new',
                priority=thread.priority,  # Inherit the priority
                has_image=bool(image_url),
                image_url=image_url,
                # If the original message was assigned, keep the same assignment
                assigned_to=thread.assigned_to
            )
            
            # Update original thread timestamp to show activity
            thread.updated_at = timezone.now()
            thread.save(update_fields=['updated_at'])
            
            # Format the response
            response_data = {
                'id': reply_thread.id,
                'subject': reply_thread.subject,
                'text': reply_thread.message,
                'sender': {
                    'id': user.id,
                    'name': user.get_full_name(),
                    'is_farmer': True
                },
                'created_at': reply_thread.created_at.isoformat(),
                'has_image': reply_thread.has_image,
                'image_url': image_url if reply_thread.has_image else None,
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)
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
    else:
        # Always update the updated_at field to show activity
        thread.updated_at = timezone.now()
        thread.save(update_fields=['updated_at'])
    
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
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_media(request):
    """
    Handle file uploads for chat messages with dual-upload support.
    
    This endpoint supports two modes of operation:
    1. Direct file upload (multipart/form-data)
    2. Base64 encoded file data (for WebSocket fallback)
    
    Expected format (multipart/form-data):
    - file: The file to upload (required)
    - thread_id: ID of the chat thread (required)
    - message_type: Type of message (e.g., 'image', 'document', 'audio', 'video')
    - caption: Optional caption for the media
    
    Expected format (JSON with base64 data):
    {
        "file_data": "base64_encoded_file_data",
        "file_name": "original_filename.ext",
        "mime_type": "file/mimetype",
        "thread_id": 123,
        "message_type": "image",
        "caption": "Optional caption"
    }
    
    Returns:
    {
        "success": true,
        "media_id": "unique_media_id",
        "media_url": "https://your-cdn.com/media/unique_media_id",
        "file_name": "original_name.jpg",
        "file_size": 12345,
        "mime_type": "image/jpeg",
        "message_type": "image",
        "uploaded_at": "2023-11-07T10:30:00Z"
    }
    """
    logger.info(f"Upload media request received. User: {request.user}")
    
    # Ensure we have a user object
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        logger.warning("No authenticated user found")
        return Response(
            {'error': 'No authenticated user found'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Handle base64 encoded file data (WebSocket fallback)
        if not request.FILES and 'file_data' in request.data:
            return handle_base64_upload(request)
            
        # Handle multipart file upload
        return handle_multipart_upload(request)
        
    except Exception as e:
        logger.error(f"Error in upload_media: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Failed to process file upload: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def handle_multipart_upload(request):
    """Handle file upload via multipart/form-data."""
    if 'file' not in request.FILES:
        logger.error("No file provided in request.FILES")
        return Response(
            {'error': 'No file provided'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    file_obj = request.FILES['file']
    thread_id = request.data.get('thread_id')
    message_type = request.data.get('message_type', 'document')
    caption = request.data.get('caption', '')
    
    # Log file details
    logger.info(f"Processing multipart upload - Name: {file_obj.name}, Size: {file_obj.size} bytes, "
                f"Content-Type: {file_obj.content_type}")
    
    # Validate file has content
    if not file_obj or file_obj.size == 0:
        logger.error("Uploaded file is empty (0 bytes)")
        return Response(
            {'error': 'Uploaded file is empty'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate required fields
    if not thread_id:
        logger.error("Thread ID is required but not provided")
        return Response(
            {'error': 'Thread ID is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if file_obj.size > max_size:
        logger.error(f"File size {file_obj.size} bytes exceeds maximum allowed size of {max_size} bytes")
        return Response(
            {'error': f'File size exceeds maximum allowed size of {max_size/1024/1024}MB'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Get the thread to ensure the user has permission
    try:
        thread = FarmerMessage.objects.get(id=thread_id)
        user = request.user
        
        # Check if the user is part of this conversation
        if user.is_farmer and thread.farmer_phone != user.phone_number:
            return Response(
                {'error': 'You do not have permission to add to this conversation'},
                status=status.HTTP_403_FORBIDDEN
            )
        if not user.is_farmer and thread.assigned_to != user and not user.is_staff:
            return Response(
                {'error': 'You are not assigned to this conversation'},
                status=status.HTTP_403_FORBIDDEN
            )
    except FarmerMessage.DoesNotExist:
        return Response(
            {'error': 'Chat thread not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error validating thread access: {str(e)}")
        return Response(
            {'error': 'Error validating thread access'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    try:
        # Determine the message type based on file content type if not provided
        if message_type not in dict(ChatMedia.MEDIA_TYPES).keys():
            if file_obj.content_type.startswith('image/'):
                message_type = 'image'
            elif file_obj.content_type.startswith('audio/'):
                message_type = 'audio'
            elif file_obj.content_type.startswith('video/'):
                message_type = 'video'
            else:
                message_type = 'document'
        
        # Save the file using the ChatMedia model
        media = ChatMedia(
            file=file_obj,
            file_name=file_obj.name,
            file_size=file_obj.size,
            mime_type=file_obj.content_type,
            message_type=message_type,
            uploaded_by=request.user
        )
        media.save()
        
        # For images, update the thread's image fields if not already set
        if media.is_image and not thread.image_file:
            thread.image_file = media.file
            thread.has_image = True
            thread.save()
        
        # ALWAYS send WebSocket acknowledgment after successful upload
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            group_name = f'thread_{thread_id}'
            
            logger.info(f"Sending WebSocket ack to group '{group_name}' for media_id: {media.id}")
            
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'media_uploaded',
                    'media_id': str(media.id),
                    'status': 'uploaded',
                    'media_url': media.get_absolute_url(),
                    'uploaded_by': request.user.id,
                    'timestamp': media.uploaded_at.isoformat()
                }
            )
            logger.info(f"SUCCESS: WebSocket ack sent to channel layer for media_id: {media.id}")
        except Exception as ack_error:
            logger.error(f"ERROR: Failed to send WebSocket ack: {str(ack_error)}", exc_info=True)
            # Don't fail the upload if ack fails
        
        # Prepare response data
        response_data = {
            'success': True,
            'media_id': str(media.id),
            'media_url': media.get_absolute_url(),
            'file_name': media.file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type,
            'message_type': media.message_type,
            'uploaded_at': media.uploaded_at.isoformat()
        }
        
        logger.info(f"Successfully uploaded file: {media.file_name} (ID: {media.id})")
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error uploading file {file_obj.name}: {str(e)}", exc_info=True)
        return Response(
            {'success': False, 'error': f'Failed to process file upload: {str(e)}'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def handle_base64_upload(request):
    """Handle file upload via base64 encoded data (WebSocket fallback)."""
    try:
        file_data = request.data.get('file_data')
        file_name = request.data.get('file_name', 'file.bin')
        mime_type = request.data.get('mime_type', 'application/octet-stream')
        thread_id = request.data.get('thread_id')
        message_type = request.data.get('message_type', 'document')
        caption = request.data.get('caption', '')
        
        if not file_data:
            return Response(
                {'success': False, 'error': 'No file data provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Validate required fields
        if not thread_id:
            return Response(
                {'success': False, 'error': 'Thread ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Decode base64 data
        try:
            if ';base64,' in file_data:
                # Handle data URL format: data:image/png;base64,...
                file_format, file_data = file_data.split(';base64,')
                mime_type = mime_type or file_format.split(':')[-1]
            
            file_binary = base64.b64decode(file_data)
            file_size = len(file_binary)
            
            # Validate file size (max 10MB)
            max_size = 10 * 1024 * 1024  # 10MB
            if file_size > max_size:
                return Response(
                    {'success': False, 'error': f'File size exceeds maximum allowed size of {max_size/1024/1024}MB'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Save the file using the ChatMedia model
            media = ChatMedia(
                file=ContentFile(file_binary, name=file_name),
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
                message_type=message_type,
                uploaded_by=request.user
            )
            media.save()
            
            # Get the thread to ensure the user has permission
            thread = FarmerMessage.objects.get(id=thread_id)
            
            # For images, update the thread's image fields if not already set
            if media.is_image and not thread.image_file:
                thread.image_file = media.file
                thread.has_image = True
                thread.save()
            
            # Prepare response data
            response_data = {
                'success': True,
                'media_id': str(media.id),
                'media_url': media.get_absolute_url(),
                'file_name': media.file_name,
                'file_size': media.file_size,
                'mime_type': media.mime_type,
                'message_type': media.message_type,
                'uploaded_at': media.uploaded_at.isoformat()
            }
            
            logger.info(f"Successfully uploaded base64 file: {media.file_name} (ID: {media.id})")
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error processing base64 file: {str(e)}", exc_info=True)
            return Response(
                {'success': False, 'error': f'Failed to process file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Exception as e:
        logger.error(f"Error in handle_base64_upload: {str(e)}", exc_info=True)
        return Response(
            {'success': False, 'error': f'Failed to process base64 upload: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


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
