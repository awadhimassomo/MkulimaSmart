import json
import logging
import base64
import uuid
from datetime import datetime, timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from .models import ChatMedia, FarmerMessage, GovernmentReply

logger = logging.getLogger('gova_pp')

class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling real-time chat and file sharing.
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.thread_id = self.scope['url_route']['kwargs'].get('thread_id')
        self.thread_group_name = f'chat_{self.thread_id}'
        self.user = self.scope["user"]
        
        # Reject connection if user is not authenticated
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return
            
        # Verify user has access to this thread
        if not await self.verify_thread_access():
            await self.close(code=4003)
            return
            
        # Join thread group
        await self.channel_layer.group_add(
            self.thread_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connected for user {self.user.id} to thread {self.thread_id}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'thread_group_name'):
            await self.channel_layer.group_discard(
                self.thread_group_name,
                self.channel_name
            )
        logger.info(f"WebSocket disconnected for user {getattr(self, 'user', 'unknown')}")
    
    @database_sync_to_async
    def verify_thread_access(self):
        """Verify user has access to the chat thread."""
        try:
            thread = FarmerMessage.objects.get(id=self.thread_id)
            if self.user.is_farmer:
                return thread.farmer_phone == self.user.phone_number
            return thread.assigned_to == self.user or self.user.is_staff
        except FarmerMessage.DoesNotExist:
            return False
    
    async def receive(self, text_data=None, bytes_data=None):
        """
        Handle incoming WebSocket messages.
        
        Expected message types:
        - media_reference: Reference to an uploaded media file
        - media_data: Encrypted media data
        - media_ack: Acknowledgment of received media
        - text_message: Regular text message
        """
        try:
            if text_data:
                data = json.loads(text_data)
                message_type = data.get('type')
                
                if message_type == 'media_reference':
                    await self.handle_media_reference(data)
                elif message_type == 'media_data':
                    await self.handle_media_data(data)
                elif message_type == 'media_ack':
                    await self.handle_media_ack(data)
                elif message_type == 'text_message':
                    await self.handle_text_message(data)
                elif message_type == 'message_new':
                    await self.handle_message_new(data)
                else:
                    logger.warning(f"Unknown message type: {message_type}")
                    await self.send_error("unknown_message_type", "Unsupported message type")
            
            elif bytes_data:
                # Handle binary data (if needed for direct file transfer)
                await self.handle_binary_data(bytes_data)
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            await self.send_error("invalid_json", "Invalid JSON format")
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.send_error("processing_error", str(e))
    
    async def handle_media_reference(self, data):
        """Handle media reference message."""
        try:
            media_info = data.get('message', {})
            media_id = media_info.get('media', {}).get('id')
            
            if not media_id:
                raise ValueError("Missing media ID in media reference")
            
            # Verify media exists and user has access
            media = await self.get_media(media_id)
            if not media:
                raise ValueError("Media not found or access denied")
            
            # Create a message record for this media
            message = await self.create_message(
                thread_id=self.thread_id,
                user_id=self.user.id,
                text=media_info.get('text', ''),
                media_id=media_id
            )
            
            # Broadcast to all in the thread
            await self.channel_layer.group_send(
                self.thread_group_name,
                {
                    'type': 'chat_message',
                    'message': {
                        'id': str(message.id),
                        'text': message.text,
                        'media': {
                            'id': str(media.id),
                            'url': media.get_absolute_url(),
                            'type': media.message_type,
                            'file_name': media.file_name,
                            'file_size': media.file_size,
                            'mime_type': media.mime_type,
                            'upload_timestamp': media.uploaded_at.isoformat()
                        },
                        'sender_id': self.user.id,
                        'sender_name': self.user.get_full_name(),
                        'timestamp': message.created_at.isoformat(),
                        'type': 'media'
                    }
                }
            )
            
            # Send acknowledgment
            await self.send_ack(media_id, 'received')
            
        except Exception as e:
            logger.error(f"Error handling media reference: {str(e)}", exc_info=True)
            await self.send_error("media_reference_error", str(e))
    
    async def handle_media_data(self, data):
        """Handle encrypted media data message."""
        try:
            media_id = data.get('media_id')
            media_data = data.get('data', {})
            
            if not all(key in media_data for key in ['key', 'iv', 'encrypted_data']):
                raise ValueError("Missing required encryption data")
            
            # In a real implementation, you would:
            # 1. Decrypt the data using the provided key and IV
            # 2. Verify the decrypted data
            # 3. Store the encrypted data as a backup
            
            # For now, we'll just log and acknowledge
            logger.info(f"Received encrypted media data for media_id: {media_id}")
            
            # Send acknowledgment
            await self.send_ack(media_id, 'received')
            
        except Exception as e:
            logger.error(f"Error handling media data: {str(e)}", exc_info=True)
            await self.send_error("media_data_error", str(e))
    
    async def handle_media_ack(self, data):
        """Handle media acknowledgment message."""
        media_id = data.get('media_id')
        status = data.get('status')
        logger.info(f"Media {media_id} status: {status}")
    
    async def handle_text_message(self, data):
        """Handle regular text message."""
        try:
            text = data.get('message', {}).get('text', '').strip()
            if not text:
                raise ValueError("Message text cannot be empty")
            
            # Create message in database
            message = await self.create_message(
                thread_id=self.thread_id,
                user_id=self.user.id,
                text=text
            )
            
            # Broadcast to all in the thread
            await self.channel_layer.group_send(
                self.thread_group_name,
                {
                    'type': 'chat_message',
                    'message': {
                        'id': str(message.id),
                        'text': message.text,
                        'sender_id': self.user.id,
                        'sender_name': self.user.get_full_name(),
                        'timestamp': message.created_at.isoformat(),
                        'type': 'text'
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling text message: {str(e)}", exc_info=True)
            await self.send_error("text_message_error", str(e))
    
    async def handle_binary_data(self, bytes_data):
        """Handle binary data (for direct file transfer if needed)."""
        logger.info(f"Received binary data: {len(bytes_data)} bytes")
        # In a real implementation, you would process the binary data here
        # For now, we'll just acknowledge receipt
        await self.send_ack("binary_data", "received")
    
    async def handle_message_new(self, data):
        """Handle message_new type from client (flat structure)."""
        try:
            text = data.get('text', '').strip()
            if not text:
                raise ValueError("Message text cannot be empty")
            
            # Create message in database
            message = await self.create_message(
                thread_id=self.thread_id,
                user_id=self.user.id,
                text=text
            )
            
            # Broadcast to all in the thread
            await self.channel_layer.group_send(
                self.thread_group_name,
                {
                    'type': 'chat_message',
                    'message': {
                        'id': str(message.id),
                        'text': message.text,
                        'sender_id': self.user.id,
                        'sender_name': self.user.get_full_name(),
                        'timestamp': message.created_at.isoformat(),
                        'type': 'text'
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling message_new: {str(e)}", exc_info=True)
            await self.send_error("message_error", str(e))

    async def chat_message(self, event):
        """Send chat message to WebSocket."""
        # Flatten the message for the client and use 'message_new' type
        message_data = event['message']
        response = {
            'type': 'message_new',
            **message_data
        }
        await self.send(text_data=json.dumps(response))
    
    async def send_ack(self, media_id, status):
        """Send acknowledgment for a media message."""
        await self.send(text_data=json.dumps({
            'type': 'media_ack',
            'media_id': media_id,
            'status': status
        }))
    
    async def send_error(self, error_type, message):
        """Send error message to WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'error': {
                'type': error_type,
                'message': message
            }
        }))
    
    @database_sync_to_async
    def get_media(self, media_id):
        """Get media by ID if user has access."""
        try:
            media = ChatMedia.objects.get(id=media_id)
            if media.uploaded_by != self.user:
                # Check if user has access to the thread this media belongs to
                if not FarmerMessage.objects.filter(
                    id=self.thread_id,
                    messages__media_id=media_id
                ).exists():
                    return None
            return media
        except ChatMedia.DoesNotExist:
            return None
    
    @database_sync_to_async
    def create_message(self, thread_id, user_id, text, media_id=None):
        """Create a new message in the database."""
        thread = FarmerMessage.objects.get(id=thread_id)
        
        if user_id == thread.farmer_phone:
            # This is a farmer message (new thread or reply)
            if not thread_id:
                # Create new thread
                message = FarmerMessage.objects.create(
                    farmer_name=self.user.get_full_name(),
                    farmer_phone=self.user.phone_number,
                    subject=f"Message from {self.user.get_full_name()}",
                    message=text,
                    status='new',
                    priority='medium'
                )
            else:
                # Update existing thread
                thread.message = text
                thread.save()
                return thread
        else:
            # This is a government reply
            message = GovernmentReply.objects.create(
                message=thread,
                replied_by_id=user_id,
                reply_text=text
            )
            
            # Update thread status
            thread.status = 'in_progress' if thread.status == 'new' else thread.status
            thread.assigned_to_id = user_id
            thread.save()
        
        return message
