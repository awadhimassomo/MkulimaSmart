from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from .models import FarmerMessage, GovernmentReply
import logging

# Set up logging
logger = logging.getLogger('gova_pp')


@api_view(['GET', 'POST'])
@permission_classes([permissions.IsAuthenticated])
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
@permission_classes([permissions.IsAuthenticated])
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
@permission_classes([permissions.IsAuthenticated])
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
