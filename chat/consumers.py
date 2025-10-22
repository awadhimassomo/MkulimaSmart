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
    async def connect(self):
        self.thread_id = self.scope["url_route"]["kwargs"]["thread_id"]
        self.group_name = f"thread_{self.thread_id}"
        
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
        
        logger.info(f"[WEBSOCKET] ACCEPTED - thread_id: {self.thread_id}, user: {user.id}")
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Handle case where connection failed before group_name was set
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"WebSocket disconnected - code: {close_code}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except Exception:
            return

        t = data.get("type")
        if t == "message_new":
            msg = await self._create_message(data)
            event = {
                "type": "broadcast",
                "event": "message_new",
                "sender_channel": self.channel_name,  # Track who sent this message
                "payload": {
                    "id": str(msg.id), 
                    "text": msg.reply_text, 
                    "sender": msg.replied_by_id,
                    "created_at": msg.created_at.isoformat()
                }
            }
            await self.channel_layer.group_send(self.group_name, event)
        elif t in ("typing_start", "typing_stop"):
            await self.channel_layer.group_send(self.group_name, {
                "type": "broadcast", 
                "event": t, 
                "payload": {"user": self.scope["user"].id}
            })

    async def broadcast(self, event):
        # Skip sending to the sender to prevent message duplication
        sender_channel = event.get("sender_channel")
        if sender_channel and sender_channel == self.channel_name:
            # Don't send the message back to the sender
            return
        
        await self.send(text_data=json.dumps({"type": event["event"], **event["payload"]}))
        
    async def message_created(self, event):
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
    def _create_message(self, data):
        return GovernmentReply.objects.create(
            message_id=self.thread_id,
            replied_by=self.scope["user"],
            reply_text=data.get("text", ""),
            reply_type='answer',
        )
