import base64
import hashlib
import json
import logging
import traceback
from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.http import FileResponse, Http404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework import status
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import ObjectDoesNotExist

from .models import Thread, ThreadParticipant, Message, Media, MediaKeyWrap
from .utils import BinaryAwareJSONEncoder

# Import the old FarmerMessage model for compatibility during transition
from gova_pp.models import FarmerMessage

# Set up logger
logger = logging.getLogger('chat')


def ws_test(request):
    """Simple view to render WebSocket test page"""
    return render(request, 'chat/ws_test.html')


class MediaRetrieveView(APIView):
    """Serve encrypted media files to authenticated users"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, media_id):
        logger.info(f"Media request received for ID: {media_id} from user: {request.user.id}")
        # Get the media object or return 404
        try:
            media = Media.objects.get(id=media_id)
        except Media.DoesNotExist:
            logger.error(f"Media not found: {media_id}")
            raise Http404("Media not found")
        
        # Check if the user has access to this media
        user = request.user
        
        # Find messages that reference this media
        messages = Message.objects.filter(media=media)
        
        if not messages.exists():
            logger.error(f"No messages found for media {media_id}")
            raise Http404("Media not found")
            
        # Check if user is a participant in any of the threads where this media appears
        authorized = False
        for msg in messages:
            if ThreadParticipant.objects.filter(thread=msg.thread, user=user).exists():
                authorized = True
                break
                
        if not authorized and not user.is_staff:
            logger.warning(f"Unauthorized media access: user={user.id}, media={media_id}")
            return Response({"error": "Not authorized to access this media"}, status=403)
        
        try:
            # Open the file and return the raw ciphertext bytes
            logger.info(f"Serving raw encrypted media file: id={media_id}, user={user.id}, size={media.size}")
            
            # Important: Always serve raw bytes for client-side decryption
            response = FileResponse(
                media.file, 
                as_attachment=False,
                content_type="application/octet-stream"  # Always use binary content type
            )
            
            # Set headers to prevent content transformation
            response['Content-Length'] = str(media.size)
            response['X-Content-Type-Options'] = 'nosniff'
            response['Cache-Control'] = 'private, max-age=3600'
            
            return response
        except Exception as e:
            logger.error(f"Error serving media file: {str(e)}")
            logger.error(traceback.format_exc())
            return Response({"error": "Error serving media file"}, status=500)


class ThreadMessageCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, thread_id: int):
        """
        Handles encrypted media uploads in chat messages
        
        Expects multipart/form-data with:
          - content (optional text)
          - encrypted_blob (File; AES-GCM ciphertext+MAC)
          - media_metadata (JSON str or JSON obj) with:
                { "sha256_hex": "...", "mime": "image/jpeg", "size": 211840,
                  "nonce_b64": "...", "width": 0, "height": 0 }
          - wrapped_keys (JSON str or JSON obj):
                { "<recipient_user_id>": "<base64 nonce+cipher+mac>" }
            or legacy:
          - wrapped_key (single base64 blob)  -> will be applied to all recipients except sender
          - thumbnail (base64 small JPEG, optional)
        """
        try:
            logger.info(f"ENCRYPTED MEDIA REQUEST - thread_id={thread_id}, user={request.user.id}")
            logger.info(f"Headers: {dict(request.headers)}")
            
            # Log request data
            data_keys = list(request.data.keys())
            files_keys = list(request.FILES.keys() if request.FILES else [])
            logger.info(f"Request data keys: {data_keys}")
            logger.info(f"Request files keys: {files_keys}")
        
            # Validate required fields early
            if 'encrypted_blob' not in request.FILES:
                return Response(
                    {"error": "encrypted_blob is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse media_metadata JSON safely
            media_metadata = None
            meta_raw = request.data.get('media_metadata', '{}')
            try:
                media_metadata = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
            except json.JSONDecodeError:
                return Response(
                    {"error": "media_metadata contains invalid JSON"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            user = request.user
            thread = None
            farmer_thread = None
            is_legacy_thread = False
        
            # Try to find thread in the new Thread model first
            try:
                thread = Thread.objects.get(id=thread_id)
                # Check membership in new thread model
                if not ThreadParticipant.objects.filter(thread=thread, user=user).exists():
                    return Response(
                        {"error": "Not in this thread"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except ObjectDoesNotExist:
                # If not found in Thread model, try the legacy FarmerMessage model
                try:
                    farmer_thread = FarmerMessage.objects.get(id=thread_id)
                    is_legacy_thread = True
                    
                    # For legacy threads, verify ownership or assignment for access
                    if user.is_farmer and farmer_thread.farmer_phone != user.phone_number:
                        return Response(
                            {"error": "Not your thread"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    elif not user.is_farmer and farmer_thread.assigned_to != user:
                        return Response(
                            {"error": "Thread not assigned to you"},
                            status=status.HTTP_403_FORBIDDEN
                        )
                    
                    # Auto-create new thread model from legacy thread
                    thread = Thread.objects.create(
                        id=farmer_thread.id,  # Use same ID for consistency
                        title=farmer_thread.subject,
                        created_at=farmer_thread.created_at,
                        updated_at=farmer_thread.updated_at,
                        is_group=False
                    )
                    
                    # Add the farmer as participant
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    try:
                        farmer = User.objects.get(phone_number=farmer_thread.farmer_phone)
                        ThreadParticipant.objects.create(thread=thread, user=farmer)
                    except ObjectDoesNotExist:
                        # If farmer user not found, log it but proceed
                        logger.warning(f"Farmer user not found for phone: {farmer_thread.farmer_phone}")
                        # Don't leave this as pass - explicitly return None from the except block
                    
                            # Add the assigned staff member if present
                    if farmer_thread.assigned_to:
                        ThreadParticipant.objects.create(
                            thread=thread, 
                            user=farmer_thread.assigned_to, 
                            is_admin=True
                        )
                    
                    # Log migration
                    logger.info(f"Created new Thread {thread.id} from legacy FarmerMessage {farmer_thread.id}")
                    
                    # Make sure current user is a participant
                    ThreadParticipant.objects.get_or_create(thread=thread, user=user)
                except ObjectDoesNotExist:
                    return Response(
                        {"error": "Thread not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            # Ensure current user is a participant (for both new and migrated threads)
            ThreadParticipant.objects.get_or_create(thread=thread, user=user)

            # Parse inputs
            content = request.data.get("content", "").strip()
            
            # Get encrypted blob file - This is redundant since we already checked earlier
            # but keeping for completeness of validation flow
            blob = request.FILES.get("encrypted_blob")
            if not blob:
                logger.warning("No encrypted_blob in request")
                return Response(
                    {"error": "No encrypted_blob found"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse media metadata
            media_metadata_raw = request.data.get("media_metadata")
            if not media_metadata_raw:
                logger.warning("No media_metadata in request")
                return Response(
                    {"error": "No media_metadata found"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                # Handle both string and direct JSON input
                if isinstance(media_metadata_raw, str):
                    media_metadata = json.loads(media_metadata_raw)
                else:
                    media_metadata = media_metadata_raw
                    
                # Log metadata received
                logger.info(f"Media metadata: {media_metadata}")
                
                # Extract metadata fields with fallbacks for mobile app format
                # Mobile app sends different format: original_type, encryption_algorithm, iv
                got_sha256 = media_metadata.get("sha256_hex", "")
                got_size = int(media_metadata.get("size", blob.size))
                mime = media_metadata.get("mime", media_metadata.get("original_type", "application/octet-stream"))
                
                # Handle different ways the nonce/iv might be provided
                nonce_b64 = media_metadata.get("nonce_b64", media_metadata.get("iv", ""))
                width = media_metadata.get("width", 0)
                height = media_metadata.get("height", 0)
                
                if not nonce_b64:
                    logger.warning("Missing required metadata field: nonce_b64/iv")
                    return Response(
                        {"error": "Incomplete media_metadata (requires nonce_b64 or iv)"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # If sha256 is missing, we'll generate it later from the file content
                if not got_sha256:
                    logger.warning("Missing sha256_hex, will generate from file content")
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Error parsing media_metadata: {str(e)}")
                return Response(
                    {"error": f"Invalid media_metadata format: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Parse wrapped keys for recipients
            wrapped_keys = None
            legacy_wrapped = None
            
            # Try new format first (per-recipient)
            wrapped_keys_raw = request.data.get("wrapped_keys")
            if wrapped_keys_raw:
                try:
                    if isinstance(wrapped_keys_raw, str):
                        wrapped_keys = json.loads(wrapped_keys_raw)
                    else:
                        wrapped_keys = wrapped_keys_raw
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Error parsing wrapped_keys: {str(e)}")
                    return Response(
                        {"error": f"Invalid wrapped_keys format: {str(e)}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # Try legacy format (single key)
                legacy_wrapped = request.data.get("wrapped_key")
                if not legacy_wrapped:
                    logger.warning("No wrapped_keys or wrapped_key found")
                    return Response(
                        {"error": "Missing wrapped_keys or wrapped_key"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Get optional thumbnail
            thumb_b64 = request.data.get("thumbnail")
            
            # If sha256_hex is missing, calculate it from the file content
            if not got_sha256:
                import hashlib
                sha256 = hashlib.sha256()
                for chunk in blob.chunks():
                    sha256.update(chunk)
                got_sha256 = sha256.hexdigest()
                # Reset file pointer for subsequent operations
                blob.seek(0)
                logger.info(f"Generated sha256_hex: {got_sha256[:10]}...")
            
            # Store the encrypted media file
            media = Media.objects.create(
                uploader=user,  # Set the current user as uploader
                size=got_size or blob.size,
                sha256_hex=got_sha256,
                mime=mime,
                file=blob,  # Will be saved to MEDIA_ROOT/uploads/YYYY/MM/DD/{uuid}.bin
            )
            logger.info(f"Created media record: id={media.id}, size={got_size}, sha256={got_sha256[:10]}...")
            
            # Create message row
            message = Message.objects.create(
                thread=thread,
                sender=user,
                text=content,
                media=media,
                media_nonce=base64.b64decode(nonce_b64) if nonce_b64 else None,
                thumb_b64=thumb_b64 or "",
                media_sha256_hex=got_sha256,
                created_at=timezone.now(),
                extra={"width": width, "height": height} if (width or height) else {},
            )
            logger.info(f"Created message record: id={message.id}, thread_id={thread.id}")
            
            # Store key-wraps per recipient
            recipients = (ThreadParticipant.objects
                        .filter(thread=thread)
                        .exclude(user=user)
                        .values_list("user_id", flat=True))
            
            saved_wraps = {}
            if wrapped_keys:
                for rid in recipients:
                    b64 = wrapped_keys.get(str(rid)) or wrapped_keys.get(int(rid))
                    if not b64:
                        continue
                    MediaKeyWrap.objects.create(message=message, recipient_id=rid, wrapped_key_b64=b64)
                    saved_wraps[str(rid)] = b64
            elif legacy_wrapped:
                # apply same wrap to all recipients (1:1 threads OK; groups not ideal but allowed)
                for rid in recipients:
                    MediaKeyWrap.objects.create(message=message, recipient_id=rid, wrapped_key_b64=legacy_wrapped)
                    saved_wraps[str(rid)] = legacy_wrapped
            
            # Prepare fan-out via Channels
            # Utility function to ensure all binary data is properly encoded for JSON
            def ensure_binary_encoded(obj):
                # Handle bytes directly - convert to base64 ASCII string
                if isinstance(obj, bytes):
                    return base64.b64encode(obj).decode('ascii')
                # Handle dictionaries - recursively encode all values
                elif isinstance(obj, dict):
                    return {k: ensure_binary_encoded(v) for k, v in obj.items()}
                # Handle lists - recursively encode all items
                elif isinstance(obj, list):
                    return [ensure_binary_encoded(item) for item in obj]
                # Handle tuples - convert to list and recursively encode
                elif isinstance(obj, tuple):
                    return [ensure_binary_encoded(item) for item in obj]
                # Handle objects with __dict__ attribute (custom objects)
                elif hasattr(obj, '__dict__'):
                    try:
                        # Try to encode the object's dictionary
                        return {k: ensure_binary_encoded(v) for k, v in obj.__dict__.items()}
                    except Exception:
                        # If that fails, convert to string
                        return str(obj)
                # For any other type that might fail JSON serialization
                try:
                    # Try JSON serialization as a test
                    json.dumps(obj)
                    return obj
                except (TypeError, ValueError):
                    # If that fails, convert to string
                    return str(obj)
            
            # If media_nonce was stored as binary, encode it
            nonce_b64_safe = ensure_binary_encoded(message.media_nonce) if message.media_nonce else nonce_b64
                
            # Ensure thumb_b64 is properly encoded string, not binary
            thumb_b64_safe = ensure_binary_encoded(message.thumb_b64) if message.thumb_b64 else ""
                    
            # Create payload with all necessary fields
            payload = {
                "id": message.id,
                "thread_id": thread.id,
                "type": "media",
                "sender_id": user.id,
                "content": message.text,
                "media_url": media.file.url if media else None,
                "media_sha256": got_sha256,
                "media_nonce_b64": nonce_b64_safe,
                "thumb_b64": thumb_b64_safe,
                "mime": mime,
                "size": media.size if media and hasattr(media, 'size') else 0,  # Default to 0 if size is None
                "wrapped_keys": saved_wraps,  # per-recipient
                "created_at": message.created_at.isoformat(),
                "media_id": media.id if media else 0,  # Ensure media_id is included and not null
                "media_mime": media_metadata.get("mime", "") if media_metadata else "",  # Default to empty string
            }
            
            # Ensure all binary data in the payload is properly encoded
            payload = ensure_binary_encoded(payload)
            
            # Prepare a safe response payload for both HTTP response and WebSocket
            safe_response_payload = ensure_binary_encoded(payload)
            
            # Define thread group name for WebSocket
            group_name = f"thread_{thread.id}"
            
            # Log before sending WebSocket message
            logger.info(f"Preparing to send WebSocket message for thread {thread.id}, message {message.id}")
            
            # Prepare WebSocket message data
            ws_message_data = {
                "type": "chat.message", 
                "data": safe_response_payload
            }
            
            try:
                # Get channel layer for WebSocket broadcasting
                channel_layer = get_channel_layer()
                
                if channel_layer:
                    # Send to thread group
                    async_to_sync(channel_layer.group_send)(group_name, ws_message_data)
                    logger.info(f"WebSocket message sent successfully to group {group_name}")
                    
                    # Also send to individual user channels (to support mobile app)
                    for rid in recipients:
                        user_group = f"user_{rid}"
                        logger.info(f"Broadcasting to user channel: {user_group}")
                        async_to_sync(channel_layer.group_send)(user_group, ws_message_data)
                else:
                    logger.warning("No channel layer available for WebSocket broadcast")
                    safe_response_payload["warning"] = "Message created but WebSocket layer unavailable"
            except Exception as e:
                # Log WebSocket error but still return a valid response to the client
                logger.error(f"WebSocket error: {str(e)}")
                logger.error(traceback.format_exc())
                # Add a warning to the response but still return success
                safe_response_payload["warning"] = "Message created but WebSocket notification failed"
            
            # Always return a valid HTTP response regardless of WebSocket success/failure
            return Response(
                safe_response_payload,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Error creating message: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Convert error message to string safely
            error_msg = str(e)
            
            # If the error involves binary data, ensure it's properly handled
            # This prevents UnicodeDecodeError when JSON serializing binary data
            try:
                # Ensure any binary data in the error message and response is properly encoded
                error_response = {"error": error_msg}
                safe_response = ensure_binary_encoded(error_response)
                
                return Response(
                    safe_response,
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except Exception as encode_error:
                logger.error(f"Error encoding response data: {str(encode_error)}")
                return Response(
                    {"error": "Server error processing binary data"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )


class RoomMessageCreateView(APIView):
    """
    API endpoint for handling unencrypted image uploads in chat rooms.
    This supports the legacy Room model for backwards compatibility.
    
    POST /api/rooms/<room_id>/messages/
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, room_id: int):
        user = request.user
        logger.info(f"Handling unencrypted message upload for room {room_id}")
        
        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            logger.warning(f"Room {room_id} not found")
            return Response({"error": "Room not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if user has access to this room
        if not room.members.filter(id=user.id).exists():
            logger.warning(f"User {user.id} not authorized for room {room_id}")
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        # Get message text
        content = request.data.get('message', '')
        
        # Handle file upload if present
        media_file = None
        media = None
        media_url = None
        if request.FILES and 'image' in request.FILES:
            media_file = request.FILES['image']
            logger.info(f"Received unencrypted image: {media_file.name}, size: {media_file.size}, type: {media_file.content_type}")
            
            # Create a new Media object
            media = Media.objects.create(
                file=media_file,
                size=media_file.size,
                uploader=user,
                mime=media_file.content_type
            )
            media_url = media.file.url if media else None
        
        # Create message record
        message = FarmerMessage.objects.create(
            room=room,
            sender=user,
            content=content,
            has_media=bool(media_file)
        )
        logger.info(f"Created unencrypted message record: id={message.id}, room_id={room_id}")
        
        # Prepare response
        payload = {
            "id": message.id,
            "room_id": room.id,
            "sender_id": user.id,
            "content": content,
            "media_url": media_url,
            "created_at": message.created_at.isoformat() if hasattr(message, 'created_at') else datetime.now().isoformat(),
        }
        
        # Log before sending WebSocket message
        logger.info(f"Preparing to send WebSocket message for room {room.id}, message {message.id}")
        
        try:
            channel_layer = get_channel_layer()
            message_data = {
                "type": "message.created",
                "room_id": room.id,
                "message_id": message.id,
                "sender_id": user.id,
                "sender_name": user.get_full_name() or user.username or user.phone_number,
                "content": content,
                "has_media": bool(media_file),
                "media_id": media.id if media else None,
                "media_url": media_url,
                "timestamp": datetime.now().isoformat()
            }
            logger.info(f"WebSocket payload: {message_data}")
            
            # Broadcast to room group
            async_to_sync(channel_layer.group_send)(
                f"room_{room.id}",
                message_data
            )
            logger.info("WebSocket message sent successfully")
            
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {str(e)}")
        
        return Response(payload, status=status.HTTP_201_CREATED)
