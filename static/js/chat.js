// WebSocket Chat Functionality for Mkulima Smart with E2E Encryption Support

// Check if crypto-utils.js is loaded and use its functions, otherwise use local implementations
// This allows the file to work both standalone and with the external utility file

// URL-safe base64 support and Uint8 helpers
const b64ToBytes = (b64) => {
  if (typeof b64ToArrayBuffer === 'function') {
    return new Uint8Array(b64ToArrayBuffer(b64));
  }
  
  // Fallback implementation
  b64 = b64.replace(/-/g, '+').replace(/_/g, '/');
  const pad = b64.length % 4 === 0 ? 0 : 4 - (b64.length % 4);
  if (pad) b64 += '='.repeat(pad);
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
};

const bytesToBlobUrl = (bytes, mime) => {
  if (typeof arrayBufferToObjectUrl === 'function') {
    return arrayBufferToObjectUrl(bytes.buffer, mime);
  }
  
  // Fallback implementation
  const blob = new Blob([bytes], { type: mime || 'application/octet-stream' });
  return URL.createObjectURL(blob);
};

// Get user's private key (uses crypto-utils.js if available or falls back to local implementation)
async function getUserPrivateKey() {
  // First check if we already have the key in memory
  if (window.userPrivateKey) return window.userPrivateKey;
  
  // Check if we have the getPrivateKey function from crypto-utils.js
  if (typeof getPrivateKey === 'function') {
    try {
      // Use the utility function to get the private key
      return await getPrivateKey();
    } catch (error) {
      console.error('Error retrieving private key from crypto-utils:', error);
    }
  }
  
  // Fallback to raw key mode for testing
  if (window.rawAesKeys && window.rawAesKeys[window.chatManager?.userId]) {
    return null; // Return null to signal using raw keys mode
  }
  
  console.warn('No private key available. Import it or switch to raw key mode for testing');
  return null;
}

// AES-GCM key handling - supports both wrapped (RSA-OAEP) and raw keys
async function getAesGcmKey({ wrappedKeyB64, isWrapped=true }) {
  // First check if the unwrapAesKey function is available from crypto-utils.js
  if (isWrapped && typeof unwrapAesKey === 'function') {
    try {
      // Use the utility function to unwrap the AES key
      return await unwrapAesKey(wrappedKeyB64);
    } catch (error) {
      console.error('Error unwrapping key with crypto-utils:', error);
      // Fall through to legacy implementation
    }
  }
  
  // Legacy implementation/fallback
  const raw = b64ToBytes(wrappedKeyB64);
  if (isWrapped) {
    const priv = await getUserPrivateKey(); // CryptoKey (RSA-OAEP)
    if (!priv) {
      console.warn('No private key available, trying to use raw key');
      // Fallback to raw key mode for testing
      return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['decrypt']);
    }
    
    const unwrapped = await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, priv, raw);
    return crypto.subtle.importKey('raw', unwrapped, { name: 'AES-GCM' }, false, ['decrypt']);
  } else {
    // Raw AES key delivered (for testing or via secure session key)
    return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['decrypt']);
  }
}

// Core decryption function
async function decryptAndRenderImage({
  containerEl,      // <div> where image should appear
  mediaUrl,         // /chat/media/{id}/ (returns ciphertext+tag)
  nonceB64,         // base64 IV (12 bytes recommended for GCM)
  wrappedKeyB64,    // per-user wrapped key (base64)
  mimeType          // e.g., 'image/jpeg' or 'image/png'
}) {
  containerEl.innerHTML = `
    <div class="relative border border-gray-200 rounded p-2 bg-gray-50">
      <div class="flex justify-center items-center p-4 bg-gray-100 rounded">
        <div class="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2"></div>
      </div>
      <div class="text-xs text-center text-blue-500 mt-1">Decrypting image…</div>
    </div>`;

  try {
    // 1) Fetch ciphertext (must be bytes; ensure server sends binary with correct auth)
    const resp = await fetch(mediaUrl, { credentials: 'include' });
    if (!resp.ok) throw new Error(`Media fetch failed: ${resp.status}`);
    const cipherBuf = await resp.arrayBuffer();

    // 2) Import/unwrap AES-GCM key
    // For testing, use isWrapped: false if your server sends raw AES keys
    const isWrapped = !window.useRawKeys; // Global flag for testing
    const aesKey = await getAesGcmKey({ wrappedKeyB64, isWrapped });

    // 3) Prepare IV
    const iv = b64ToBytes(nonceB64); // must be 12 bytes for GCM
    if (iv.byteLength !== 12) throw new Error(`Invalid IV length: ${iv.byteLength}`);

    // 4) Decrypt (ciphertext MUST include the GCM auth tag appended by the server)
    let plain;
    try {
      // Check if we have the decryptData function from crypto-utils.js
      if (typeof decryptData === 'function') {
        plain = await decryptData(cipherBuf, aesKey, iv);
      } else {
        // Fallback to built-in implementation
        plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, aesKey, cipherBuf);
      }
    } catch (e) {
      // Common causes: wrong key/iv, truncated file, tag mismatch, or different AAD used server-side
      throw new Error(`AES-GCM decrypt failed: ${e.message || e.name}`);
    }

    // 5) Render
    const url = bytesToBlobUrl(new Uint8Array(plain), mimeType || 'image/jpeg');
    containerEl.innerHTML = `
      <div class="relative border border-gray-200 rounded p-2 bg-gray-50">
        <img src="${url}" alt="Decrypted image" class="rounded max-w-full max-h-[360px]" />
        <div class="text-[10px] text-gray-500 mt-1">End-to-end decrypted</div>
      </div>`;
  } catch (err) {
    console.error('Decryption error:', err);
    containerEl.innerHTML = `
      <div class="p-3 bg-red-50 text-red-700 rounded border">
        Failed to decrypt image: ${err.message}
      </div>`;
  }
}
class ChatManager {
    constructor(threadId, userId) {
        this.threadId = threadId;
        this.userId = userId;
        this.socket = null;
        this.connected = false;
        this.messageQueue = [];
        this.typingUsers = new Set();
        this.typingTimer = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        // Encryption key cache (to avoid asking for key multiple times)
        this.mediaKeys = {};
    }
    
    // Add a thumbnail or icon for the message based on MIME type
    createMediaThumbnail(mimeType) {
        // Helper to create default thumbnails for different media types
        if (mimeType?.startsWith('image/')) {
            return `
                <div class="flex items-center justify-center p-4 bg-gray-100 rounded h-20 w-20">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                </div>
            `;
        } else if (mimeType?.startsWith('video/')) {
            return `
                <div class="flex items-center justify-center p-4 bg-gray-100 rounded h-20 w-20">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                </div>
            `;
        } else if (mimeType?.startsWith('audio/')) {
            return `
                <div class="flex items-center justify-center p-4 bg-gray-100 rounded h-20 w-20">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                    </svg>
                </div>
            `;
        } else {
            return `
                <div class="flex items-center justify-center p-4 bg-gray-100 rounded h-20 w-20">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                    </svg>
                </div>
            `;
        }
    }
    
    // Handle encrypted media with proper client-side decryption
    async handleEncryptedMedia(mediaId, mediaUrl, nonce_b64, wrapped_key, mimeType) {
        try {
            console.log('Handling encrypted media with decryption:', mediaId, mediaUrl);
            
            if (!mediaId || !mediaUrl || !nonce_b64 || !wrapped_key) {
                console.error('Missing required parameters for decryption');
                return `
                    <div class="p-3 bg-red-50 text-red-700 rounded border">
                        Missing encryption parameters. Cannot decrypt media.
                    </div>
                `;
            }
            
            // Create container ID for this media
            const containerDivId = `media-container-${mediaId}`;
            
            // Return a container div that will be populated by the decryption function
            return `
                <div id="${containerDivId}" class="media-container">
                    <div class="flex items-center justify-center p-4 bg-gray-100 rounded">
                        <div class="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2"></div>
                    </div>
                    <div class="text-xs text-center text-blue-500 mt-1">Preparing to decrypt...</div>
                </div>
                <script>
                    // Execute decryption after the container is in DOM
                    setTimeout(() => {
                        const container = document.getElementById('${containerDivId}');
                        if (container) {
                            decryptAndRenderImage({
                                containerEl: container,
                                mediaUrl: '${mediaUrl}',
                                nonceB64: '${nonce_b64}',
                                wrappedKeyB64: '${wrapped_key}',
                                mimeType: '${mimeType || "image/jpeg"}'
                            }).catch(err => {
                                console.error('Failed to decrypt:', err);
                            });
                        }
                    }, 100);
                </script>
            `;
        } catch (error) {
            console.error('Error handling encrypted media:', error);
            return `
                <div class="p-3 bg-red-50 text-red-700 rounded border">
                    Failed to handle encrypted media: ${error.message}
                </div>
            `;
        }
    }
    
    // Helper method to convert base64 to ArrayBuffer
    _base64ToArrayBuffer(base64) {
        const binaryString = window.atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes;
    }

    connect(token) {
        // Close existing connection if any
        if (this.socket) {
            console.log('Closing existing WebSocket connection...');
            this.socket.close();
        }

        // Create WebSocket connection
        let protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Use the same host and port as the web server
        let host = window.location.host;
        // Ensure the path matches exactly with the routing pattern
        let wsUrl = `${protocol}//${host}/ws/chat/${this.threadId}/?token=${token}`;

        console.log('Attempting WebSocket connection...');
        console.log('URL:', wsUrl.replace(token, token.substring(0, 20) + '...'));
        console.log('Protocol:', protocol);
        console.log('Host:', host);
        console.log('Thread ID:', this.threadId);

        try {
            this.socket = new WebSocket(wsUrl);
            console.log('WebSocket object created successfully');
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.updateConnectionStatus(false);
            return;
        }

        // Connection opened
        this.socket.addEventListener('open', (event) => {
            console.log('✅ WebSocket connection established!');
            this.connected = true;
            
            // Send any queued messages
            while (this.messageQueue.length > 0) {
                const message = this.messageQueue.shift();
                this.socket.send(JSON.stringify(message));
                console.log('Sent queued message:', message);
            }
            
            // Update UI to show connected state
            this.updateConnectionStatus(true);
        });

        // Listen for messages
        this.socket.addEventListener('message', (event) => {
            const data = JSON.parse(event.data);
            this.handleIncomingMessage(data);
        });

        // Connection closed
        this.socket.addEventListener('close', (event) => {
            console.log('⚠️ WebSocket connection closed');
            console.log('Close code:', event.code);
            console.log('Close reason:', event.reason || 'No reason provided');
            console.log('Was clean:', event.wasClean);
            this.connected = false;
            this.updateConnectionStatus(false);
            
            // Try to reconnect after 5 seconds
            console.log('Will attempt reconnection in 5 seconds...');
            setTimeout(() => {
                console.log('Attempting to reconnect...');
                this.connect(token);
            }, 5000);
        });

        // Connection error
        this.socket.addEventListener('error', (error) => {
            console.error('❌ WebSocket error occurred!');
            console.error('Error details:', error);
            console.error('Ready state:', this.socket.readyState);
            console.error('Ready states: CONNECTING=0, OPEN=1, CLOSING=2, CLOSED=3');
            this.connected = false;
            this.updateConnectionStatus(false);
        });
    }

    handleIncomingMessage(data) {
        console.log('📨 Received message:', data);
        
        const messageType = data.type;
        
        // Handle different message types
        switch (messageType) {
            case 'message_new':
                // Skip messages from current user (already added optimistically in sendMessage)
                if (data.sender == this.userId) {
                    console.log('⏭️ Skipping own message from broadcast (already added optimistically)');
                    break;
                }
                this.addMessageToChat(data);
                break;
            
            case 'typing_start':
                if (data.user !== this.userId) {
                    this.showTypingIndicator(data.user);
                }
                break;
            
            case 'typing_stop':
                if (data.user !== this.userId) {
                    this.hideTypingIndicator(data.user);
                }
                break;
                
            case 'chat.message':
                // Handle chat.message events (from HTTP API)
                if (data.data) {
                    // Skip messages from current user (already added optimistically)
                    if (data.data.sender_id == this.userId) {
                        console.log('⏭️ Skipping own chat.message from broadcast (already added optimistically)');
                        break;
                    }
                    this.addMessageToChat(data.data);
                }
                break;
            
            case 'error':
                console.error('❌ WebSocket error:', data);
                this.updateConnectionStatus(false);
                break;
            
                
            default:
                console.log('Unknown message type:', messageType);
        }
    }

    updateConnectionStatus(isConnected) {
        const statusEl = document.getElementById('connection-status');
        if (!statusEl) return;
        
        if (isConnected) {
            statusEl.innerHTML = `
                <span class="w-2 h-2 rounded-full bg-green-500 mr-2"></span>
                <span class="text-green-600 font-medium">Connected</span>
            `;
            statusEl.className = 'flex items-center text-sm';
            this.connected = true;
            
            console.log('✅ WebSocket connected successfully');
            
            // Send any queued messages
            while (this.messageQueue.length > 0) {
                const message = this.messageQueue.shift();
                this.socket.send(JSON.stringify(message));
                console.log('📤 Sent queued message:', message);
            }
        } else {
            statusEl.innerHTML = `
                <span class="w-2 h-2 rounded-full bg-red-500 mr-2 animate-pulse"></span>
                <span class="text-red-600">Disconnected</span>
            `;
            statusEl.className = 'flex items-center text-sm';
            this.connected = false;
            
            console.log('❌ WebSocket disconnected');
        }
    }

    addMessageToChat(data) {
        const chatContainer = document.getElementById('chat-messages');
        if (!chatContainer) {
            console.error('Chat container not found');
            return;
        }
        
        // Remove "no messages" placeholder if exists
        const noMessagesPlaceholder = chatContainer.querySelector('.text-center.py-8');
        if (noMessagesPlaceholder) {
            noMessagesPlaceholder.remove();
        }
        
        // Handle different message formats
        let sender_id, sender_name, content, timestamp, has_media, media_url, media_id, media_type;
        
        if (data.type === 'message.created') {
            // New encrypted media format
            sender_id = data.sender_id;
            sender_name = data.sender_name || 'Unknown User';
            content = data.content;
            timestamp = data.timestamp;
            has_media = data.has_media;
            media_id = data.media_id;
            media_type = data.media_mime;
            
            // Create URL for media if available
            if (has_media && media_id) {
                media_url = `/chat/media/${media_id}/`;
            }
        } else if (data.type === 'message_new') {
            // WebSocket message format
            sender_id = data.sender || data.payload?.sender;
            sender_name = data.sender_name || 'User';
            content = data.text || data.payload?.text;
            timestamp = data.created_at || data.payload?.created_at || new Date().toISOString();
            has_media = false;
        } else {
            // Legacy format
            sender_id = data.sender;
            sender_name = data.sender_name || 'User';
            content = data.text;
            timestamp = data.created_at;
            has_media = false;
        }
        
        const isCurrentUser = sender_id == this.userId;
        
        // Get sender's first initial
        const senderInitial = sender_name.charAt(0).toUpperCase();
        
        // Format timestamp
        let formattedTime;
        try {
            const date = new Date(timestamp);
            formattedTime = date.toLocaleString('en-US', { 
                month: 'short', 
                day: 'numeric', 
                hour: 'numeric', 
                minute: '2-digit',
                hour12: true 
            });
        } catch (e) {
            formattedTime = 'Just now';
        }
        
        // Media attachment HTML if present
        let mediaHtml = '';
        if (has_media && media_url) {
            // Get additional data for decryption
            let nonce_b64 = '';
            let wrapped_key = null;
            
            // Get encryption data from different message formats
            if (data.type === 'message.created') {
                nonce_b64 = data.media_nonce_b64 || data.iv || '';
                if (data.wrapped_keys && data.wrapped_keys[this.userId]) {
                    wrapped_key = data.wrapped_keys[this.userId];
                }
            }
            
            // Process media differently for images vs other file types
            if (media_type && media_type.startsWith('image/')) {
                // Add image with loading state first
                const mediaId = `media-${data.id || Math.random().toString(36).substring(2, 15)}`;
                mediaHtml = `
                    <div class="media-container mt-2" id="container-${mediaId}">
                        <div class="relative border border-gray-200 rounded p-2 bg-gray-50">
                            <div class="flex justify-center items-center p-4 bg-gray-100 rounded">
                                <div class="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
                            </div>
                            <div class="text-xs text-center text-blue-500 mt-1">Loading image...</div>
                        </div>
                    </div>
                `;
                
                // Process the media for display
                setTimeout(async () => {
                    try {
                        // Generate the decryption HTML directly
                        const decryptionHtml = await this.handleEncryptedMedia(
                            media_id, 
                            media_url,
                            nonce_b64, 
                            wrapped_key, 
                            media_type
                        );
                        
                        // Update the container with the decryption HTML
                        const container = document.getElementById(`container-${mediaId}`);
                        if (container) {
                            container.innerHTML = decryptionHtml;
                        }
                    } catch (error) {
                        console.error('Error displaying media:', error);
                        
                        // Show error state
                        const container = document.getElementById(`container-${mediaId}`);
                        if (container) {
                            container.innerHTML = `
                                <div class="p-3 bg-red-50 text-red-700 rounded border border-red-200">
                                    <div class="flex items-center">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                        </svg>
                                        Error processing media
                                    </div>
                                    <div class="mt-1 text-xs">
                                        <a href="${media_url}" class="text-blue-600 underline" download>Download original file</a>
                                    </div>
                                </div>
                            `;
                        }
                    }
                }, 100);
            } else {
                // For non-image files, just provide a download link
                mediaHtml = `
                    <div class="media-container mt-2">
                        <div class="bg-gray-100 border border-gray-200 p-3 rounded">
                            <div class="flex items-center">
                                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                </svg>
                                <a href="${media_url}" class="text-blue-500 hover:underline" download>Download File</a>
                            </div>
                        </div>
                    </div>
                `;
            }
        }
        
        // Create message element with Mkulima Smart styling
        const messageDiv = document.createElement('div');
        messageDiv.className = `flex ${isCurrentUser ? 'justify-end' : 'justify-start'} message-item`;
        messageDiv.innerHTML = `
            <div class="max-w-md md:max-w-lg">
                <div class="${isCurrentUser ? 'bg-gradient-to-r from-[#2D5A27] to-[#4A7C3A] text-white' : 'bg-white border border-gray-200'} rounded-2xl px-4 py-3 shadow-sm animate-fadeIn">
                    <div class="flex items-center space-x-2 mb-1">
                        <div class="flex items-center space-x-2">
                            <div class="w-8 h-8 rounded-full ${isCurrentUser ? 'bg-[#C5D86D]' : 'bg-gray-300'} flex items-center justify-center text-sm font-semibold ${isCurrentUser ? 'text-[#2D5A27]' : 'text-gray-700'}">
                                ${senderInitial}
                            </div>
                            <span class="font-medium text-sm ${isCurrentUser ? '' : 'text-gray-900'}">
                                ${isCurrentUser ? 'You' : sender_name}
                            </span>
                        </div>
                    </div>
                    <p class="${isCurrentUser ? '' : 'text-gray-700'} whitespace-pre-wrap leading-relaxed">${content}</p>
                    ${mediaHtml}
                    <div class="text-xs ${isCurrentUser ? 'text-white text-opacity-80' : 'text-gray-500'} mt-2 text-right">
                        ${formattedTime}
                    </div>
                </div>
            </div>
        `;
        
        chatContainer.appendChild(messageDiv);
        
        // Smooth scroll to bottom
        chatContainer.scrollTo({
            top: chatContainer.scrollHeight,
            behavior: 'smooth'
        });
        
        // Update message count
        const messageCount = document.getElementById('message-count');
        if (messageCount) {
            const currentCount = chatContainer.querySelectorAll('.message-item').length;
            messageCount.textContent = `(${currentCount} messages)`;
        }
        
        // Play notification sound if message from other user
        if (!isCurrentUser) {
            const sound = document.getElementById('notification-sound');
            if (sound) {
                sound.play().catch(e => console.log('Could not play notification sound'));
            }
        }
        
        console.log('✅ Message added to chat:', content.substring(0, 50) + '...');
    }

    showTypingIndicator(userId) {
        if (userId == this.userId) return; // Don't show typing indicator for current user
        
        this.typingUsers.add(userId);
        const typingIndicator = document.getElementById('typing-indicator');
        
        if (typingIndicator) {
            typingIndicator.style.display = 'block';
        }
    }

    hideTypingIndicator(userId) {
        this.typingUsers.delete(userId);
        
        if (this.typingUsers.size === 0) {
            const typingIndicator = document.getElementById('typing-indicator');
            if (typingIndicator) {
                typingIndicator.style.display = 'none';
            }
        }
    }

    sendMessage(text) {
        const message = {
            type: 'message_new',
            text: text,
        };
        
        if (this.connected) {
            // Add message to chat immediately (optimistic UI update)
            this.addMessageToChat({
                type: 'message_new',
                text: text,
                sender: this.userId,
                created_at: new Date().toISOString(),
            });
            
            // Send to server
            this.socket.send(JSON.stringify(message));
            
            console.log('✅ Message sent and added to chat');
        } else {
            // Queue message to be sent when connection is established
            this.messageQueue.push(message);
        }
    }

    sendTypingStatus(isTyping) {
        if (!this.connected) return;
        
        clearTimeout(this.typingTimer);
        
        const statusType = isTyping ? 'typing_start' : 'typing_stop';
        this.socket.send(JSON.stringify({ type: statusType }));
        
        // Auto-stop typing after 3 seconds of inactivity
        if (isTyping) {
            this.typingTimer = setTimeout(() => {
                this.socket.send(JSON.stringify({ type: 'typing_stop' }));
            }, 3000);
        }
    }

    uploadFile(fileInput) {
        const file = fileInput.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('thread_id', this.threadId);
        
        const uploadStatusEl = document.getElementById('upload-status');
        if (uploadStatusEl) {
            uploadStatusEl.textContent = 'Uploading...';
            uploadStatusEl.style.display = 'block';
        }
        
        fetch('/gova-pp/api/messages/upload/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        })
        .then(response => response.json())
        .then(data => {
            if (uploadStatusEl) {
                uploadStatusEl.textContent = 'Upload complete!';
                setTimeout(() => {
                    uploadStatusEl.style.display = 'none';
                }, 3000);
            }
            
            // Clear the file input
            fileInput.value = '';
        })
        .catch(error => {
            console.error('Error uploading file:', error);
            if (uploadStatusEl) {
                uploadStatusEl.textContent = 'Upload failed. Please try again.';
                uploadStatusEl.classList.add('text-red-600');
            }
        });
    }
}

// Initialize chat on page load
document.addEventListener('DOMContentLoaded', () => {
    const threadIdEl = document.getElementById('thread-id');
    const userIdEl = document.getElementById('current-user-id');
    const tokenEl = document.getElementById('jwt-token');
    
    if (threadIdEl && userIdEl && tokenEl) {
        const threadId = threadIdEl.value;
        const userId = userIdEl.value;
        const token = tokenEl.value;
        
        window.chatManager = new ChatManager(threadId, userId);
        window.chatManager.connect(token);
        
        // Set up form submission
        const messageForm = document.getElementById('message-form');
        if (messageForm) {
            messageForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const messageInput = document.getElementById('message-input');
                const text = messageInput.value.trim();
                
                if (text) {
                    window.chatManager.sendMessage(text);
                    messageInput.value = '';
                }
            });
        }
        
        // Set up typing indicator
        const messageInput = document.getElementById('message-input');
        if (messageInput) {
            messageInput.addEventListener('input', () => {
                window.chatManager.sendTypingStatus(true);
            });
        }
        
        // Set up file upload
        const fileInput = document.getElementById('file-input');
        if (fileInput) {
            fileInput.addEventListener('change', () => {
                window.chatManager.uploadFile(fileInput);
            });
        }
    }
});
