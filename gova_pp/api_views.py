from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import FarmerMessage, GovernmentReply
import os
from django.conf import settings
from django.utils import timezone
import uuid

class MessageViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=["post"])
    def upload(self, request):
        """
        Endpoint to handle file uploads (images) for farmer messages
        and notify clients through WebSockets
        """
        if 'file' not in request.FILES:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)
            
        if 'thread_id' not in request.data:
            return Response({"error": "No thread_id provided"}, status=status.HTTP_400_BAD_REQUEST)
            
        file = request.FILES["file"]
        thread_id = request.data["thread_id"]
        
        # Check if the message exists
        try:
            message = FarmerMessage.objects.get(id=thread_id)
        except FarmerMessage.DoesNotExist:
            return Response({"error": "Message not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Save the file to storage
        filename = f"{uuid.uuid4()}_{file.name}"
        file_path = os.path.join('media', 'farmer_images', filename)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.join(settings.MEDIA_ROOT, 'farmer_images')), exist_ok=True)
        
        # Save the file
        with open(os.path.join(settings.MEDIA_ROOT, 'farmer_images', filename), 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
        
        # Create a government reply with the attachment
        file_url = f"{settings.MEDIA_URL}farmer_images/{filename}"
        
        # Create reply with attachment reference
        reply = GovernmentReply.objects.create(
            message=message,
            replied_by=request.user,
            reply_text=f"Shared an image: {file.name}",
            reply_type='answer',
        )
        
        # Update message status
        message.has_image = True
        message.image_file = f"farmer_images/{filename}"
        message.updated_at = timezone.now()
        message.save()
        
        # Notify over WebSocket
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"thread_{thread_id}",
            {
                "type": "broadcast",
                "event": "message_new",
                "payload": {
                    "id": str(reply.id), 
                    "text": reply.reply_text,
                    "sender": reply.replied_by_id,
                    "created_at": reply.created_at.isoformat(),
                    "attachments": [{"type": "image", "url": file_url}]
                }
            }
        )
        
        return Response({
            "ok": True, 
            "message_id": str(reply.id),
            "file_url": file_url
        }, status=status.HTTP_201_CREATED)
