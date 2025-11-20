import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.exceptions import PermissionDenied
from gova_pp.models import FarmerMessage, GovernmentReply
import uuid
import logging

# Set up logger
logger = logging.getLogger('gova_pp')

class ChatConsumer(AsyncWebsocketConsumer):
    # Class-level dictionary to track active connections per thread
    # Format: {thread_id: {user_id: channel_name}}
    active_channels = {}
    
    async def connect(self):
        self.thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        self.group_name = f"thread_{self.thread_id}"  # Keep for typing indicators only
        
        user = self.scope["user"]
        user_id = user.id if user.is_authenticated else "anonymous"
        user_type = 'farmer' if getattr(user, 'is_farmer', False) else 'staff/other'
        
        logger.info(f"[WEBSOCKET] Connect attempt - thread_id: {self.thread_id}, user: {user_id}, user_type: {user_type}")
        
        # Check authentication first
        if not user.is_authenticated:
            auth_error = self.scope.get("auth_error", "unknown")
            logger.warning(f"[WEBSOCKET] REJECTED - User not authenticated. Auth error: {auth_error}")
            
            # IMPORTANT: Must accept connection before sending messages
            await self.accept()
            
            # Send error message
            error_messages = {
                "no_token": "Authentication failed: No token provided",
                "invalid_token": "Authentication failed: Invalid or expired token",
                "exception": "Authentication failed: Server error during authentication",
                "unknown": "Authentication failed: Unknown error"
            }
            error_message = error_messages.get(auth_error, error_messages["unknown"])
            
            # Send error details to client
            await self.send(text_data=json.dumps({
                "type": "error",
                "code": "auth_failed",
                "message": error_message,
                "details": {
                    "reason": auth_error,
                    "thread_id": self.thread_id
                }
            }))
            
            # Close with custom code for authentication failure
            await self.close(code=4401)
            return
            
        # Now check participation
        is_participant = await self._is_participant()
        if not is_participant:
            logger.warning(f"[WEBSOCKET] REJECTED - User {user.id} is not a participant in thread {self.thread_id}")
            
            # IMPORTANT: Must accept connection before sending messages
            await self.accept()
            
            # Send error message
            await self.send(text_data=json.dumps({
                "type": "error",
                "code": "forbidden",
                "message": "You don't have permission to access this conversation",
                "details": {
                    "thread_id": self.thread_id,
                    "user_id": user.id
                }
            }))
            
            # Close with forbidden code
            await self.close(code=4403)
            return
        
        logger.info(f"[WEBSOCKET] ACCEPTED - thread_id: {self.thread_id}, user: {user_id}")
        
        # Track this connection for direct messaging
        if self.thread_id not in ChatConsumer.active_channels:
            ChatConsumer.active_channels[self.thread_id] = {}
        ChatConsumer.active_channels[self.thread_id][user_id] = self.channel_name
        
        # Add to group for typing indicators only
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        
        # Accept the connection
        await self.accept()
        logger.info(f"[WEBSOCKET] ACCEPTED - thread_id: {self.thread_id}, user: {user_id}, channel: {self.channel_name}")
        logger.info(f"[WEBSOCKET] Active channels for thread {self.thread_id}: {list(ChatConsumer.active_channels.get(self.thread_id, {}).keys())}")

    async def disconnect(self, close_code):
        user = self.scope.get("user")
        user_id = user.id if user and user.is_authenticated else "anonymous"
        
        logger.info(f"[WEBSOCKET] Disconnect - thread: {self.thread_id}, user: {user_id}, code: {close_code}")
        
        # Remove from active channels tracking
        if self.thread_id in ChatConsumer.active_channels:
            ChatConsumer.active_channels[self.thread_id].pop(user_id, None)
            if not ChatConsumer.active_channels[self.thread_id]:
                del ChatConsumer.active_channels[self.thread_id]
        
        # Leave room group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"WebSocket disconnected - code: {close_code}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except Exception as e:
            logger.error(f"[WEBSOCKET] Failed to parse message: {e}")
            return

        t = data.get("type")
        logger.info(f"[WEBSOCKET] [Thread:{self.thread_id}] Received message type: {t}")
        
        if t == "message_new":
            msg = await self._create_message(data)
            message_data = {
                "type": "message_new",
                "id": str(msg.id), 
                "text": msg.reply_text, 
                "sender": msg.replied_by_id,
                "created_at": msg.created_at.isoformat()
            }
            
            # Send directly to other participant, not via broadcast group
            await self._send_to_other_participant(message_data)
            
        elif t == "media_data" or t == "media_reference":
            # Handle media reference message from Flutter
            media_id = data.get("media_id") or data.get("data", {}).get("media_id")
            caption = data.get("caption") or data.get("text") or ""
            
            logger.info(f"[WEBSOCKET] [Thread:{self.thread_id}] Received media reference: media_id={media_id}")
            
            if media_id:
                # Get the actual media URL from the database
                media_url = data.get("media_url")
                if not media_url:
                    # Fetch from database if not provided
                    media = await self._get_media_by_id(media_id)
                    if media and media.file:
                        # Get the actual file path from the FileField
                        media_url = media.file.url  # This gives us /media/chat_media/8/2025/11/09/file.jpg
                        logger.info(f"[WEBSOCKET] Retrieved media_url from database: {media_url}")
                    else:
                        logger.error(f"[WEBSOCKET] Media not found or has no file for media_id: {media_id}")
                        media_url = None
                
                logger.info(f"[WEBSOCKET] Using media_url: {media_url}")
                
                # Create a message with the media reference
                msg = await self._create_message({"text": caption, "media_id": media_id})
                
                # Send acknowledgment back to sender
                await self.send(text_data=json.dumps({
                    "media_id": media_id,
                    "status": "received",
                    "success": True,
                    "message_id": str(msg.id) if msg else None
                }))
                
                logger.info(f"[WEBSOCKET] Broadcasting media message to group with media_url: {media_url}")
                
                # Send directly to other participant
                message_data = {
                    "type": "message_new",
                    "id": str(msg.id) if msg else None,
                    "content": caption,
                    "text": caption,
                    "media_id": media_id,
                    "media_url": media_url,
                    "has_media": True,
                    "sender_id": self.scope["user"].id,
                    "sender": self.scope["user"].id,
                    "timestamp": msg.created_at.isoformat() if msg and hasattr(msg, 'created_at') else None,
                    "created_at": msg.created_at.isoformat() if msg and hasattr(msg, 'created_at') else None
                }
                await self._send_to_other_participant(message_data)
            else:
                logger.error(f"[WEBSOCKET] No media_id found in media reference message")
                await self.send(text_data=json.dumps({
                    "error": "No media_id provided",
                    "success": False
                }))
                
        elif t in ("typing_start", "typing_stop"):
            await self.channel_layer.group_send(self.group_name, {
                "type": "broadcast", 
                "event": t, 
                "payload": {"user": self.scope["user"].id}
            })
        else:
            logger.warning(f"[WEBSOCKET] [Thread:{self.thread_id}] Unknown message type: {t}")

    async def _send_to_other_participant(self, message_data):
        """Send message directly to the other participant in the conversation"""
        current_user_id = self.scope["user"].id
        thread_channels = ChatConsumer.active_channels.get(self.thread_id, {})
        
        # Find other participants (exclude current user)
        other_channels = {uid: ch for uid, ch in thread_channels.items() if uid != current_user_id}
        
        if other_channels:
            logger.info(f"[WEBSOCKET] Sending message to {len(other_channels)} other participant(s)")
            for user_id, channel_name in other_channels.items():
                try:
                    await self.channel_layer.send(
                        channel_name,
                        {
                            "type": "direct_message",
                            "message": message_data
                        }
                    )
                    logger.info(f"[WEBSOCKET] Message sent to user {user_id} via channel {channel_name}")
                except Exception as e:
                    logger.error(f"[WEBSOCKET] Failed to send to user {user_id}: {e}")
        else:
            logger.warning(f"[WEBSOCKET] No other participants online for thread {self.thread_id}")
    
    async def direct_message(self, event):
        """Receive and forward direct messages"""
        await self.send(text_data=json.dumps(event["message"]))
    
    async def broadcast(self, event):
        """Keep for typing indicators - they still use groups"""
        sender_channel = event.get("sender_channel")
        if sender_channel and sender_channel == self.channel_name:
            return
        await self.send(text_data=json.dumps({"type": event["event"], **event["payload"]}))
        
    async def message_created(self, event):
        """Legacy handler - not used with direct messaging"""
        # Handle message.created events from the channel layer
        logger.info(f"Received message.created event: {event}")
        
        # Prepare the payload for the WebSocket client
        payload = {
            "id": event["message_id"],
            "thread_id": event["thread_id"],
            "sender_id": event["sender_id"],
            "sender_name": event["sender_name"],
            "content": event["content"],
            "has_media": event["has_media"],
            "media_id": event["media_id"],
            "media_mime": event["media_mime"],
            "timestamp": event["timestamp"],
        }
        
        # Send the message to WebSocket
        await self.send(text_data=json.dumps({
            "type": "message.created",
            **payload
        }))
    
    async def media_uploaded(self, event):
        """Handle media upload acknowledgment events from the channel layer"""
        media_id = event["media_id"]
        user = self.scope.get("user")
        user_id = user.id if user and hasattr(user, 'id') else 'unknown'
        
        logger.info(f"[WEBSOCKET] [Thread:{self.thread_id}] [User:{user_id}] Received media_uploaded event for media_id: {media_id}")
        
        # Send acknowledgment to WebSocket client in the format Flutter app expects
        # Flutter checks: status == 'received' OR success == true
        ack_message = {
            "media_id": media_id,
            "status": "received",  # Flutter expects "received" not "uploaded"
            "success": True,       # Flutter also checks for success == true
            "type": "media_ack",   # Optional but good practice
            "media_url": event.get("media_url"),
            "uploaded_by": event.get("uploaded_by"),
            "timestamp": event.get("timestamp")
        }
        
        logger.info(f"[WEBSOCKET] [Thread:{self.thread_id}] [User:{user_id}] Sending ack to client: {json.dumps(ack_message)}")
        await self.send(text_data=json.dumps(ack_message))
        logger.info(f"[WEBSOCKET] [Thread:{self.thread_id}] [User:{user_id}] SUCCESS: Ack sent via WebSocket for media_id: {media_id}")

    @database_sync_to_async
    def _is_participant(self):
        # Check if the user is assigned to this message or is an admin
        message = FarmerMessage.objects.filter(id=self.thread_id).first()
        if not message:
            logger.info(f"WebSocket auth check - Thread {self.thread_id} not found")
            return False
            
        user = self.scope["user"]
        
        # Debug message details
        logger.info(f"WebSocket auth check - Thread: {self.thread_id}, Message details: farmer_phone={message.farmer_phone}, assigned_to_id={message.assigned_to_id}, user.id={user.id}, user.is_farmer={getattr(user, 'is_farmer', False)}, user.is_staff={getattr(user, 'is_staff', False)}")
        
        # Allow if user is:
        # 1. The farmer who created the message (match by phone number if user is a farmer)
        # 2. The staff user assigned to the message
        # 3. Any staff user (admin access)
        if hasattr(user, 'phone_number') and user.is_farmer and user.phone_number == message.farmer_phone:
            logger.info(f"WebSocket auth success - User {user.id} phone matches the farmer who created this thread")
            return True
        elif message.assigned_to_id == user.id:
            logger.info(f"WebSocket auth success - User {user.id} is assigned to this thread")
            return True
        elif getattr(user, 'is_staff', False):
            logger.info(f"WebSocket auth success - User {user.id} has staff privileges")
            return True
        
        logger.info(f"WebSocket auth failed - User {user.id} has no permission for thread {self.thread_id}")
        return False

    @database_sync_to_async
    def _get_media_by_id(self, media_id):
        """Get media object by ID"""
        try:
            from gova_pp.models import ChatMedia  # ChatMedia is in gova_pp, not chat
            return ChatMedia.objects.get(id=media_id)
        except Exception as e:
            logger.error(f"Error fetching media: {e}")
            return None
    
    @database_sync_to_async
    def _create_message(self, data):
        return GovernmentReply.objects.create(
            message_id=self.thread_id,
            replied_by=self.scope["user"],
            reply_text=data.get("text", ""),
            reply_type='answer',
        )
