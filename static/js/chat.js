// WebSocket Chat Functionality for Mkulima Smart

// Utility functions
function b64ToBytes(b64) {
    const binaryString = window.atob(b64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
}

function bytesToBlobUrl(bytes, mime) {
    const blob = new Blob([bytes], { type: mime });
    return URL.createObjectURL(blob);
}

// Get user's private key
async function getUserPrivateKey() {
    // Implementation for getting private key
    return null;
}

// AES-GCM key handling
async function getAesGcmKey({ wrappedKeyB64, isWrapped = true }) {
    // Implementation for getting AES-GCM key
    return null;
}

// Core decryption function
async function decryptAndRenderImage({ containerEl, mediaUrl, nonceB64, wrappedKeyB64, mimeType }) {
    try {
        if (!containerEl || !mediaUrl) {
            console.error('Missing required parameters for decryptAndRenderImage');
            return;
        }

        // Show loading state
        containerEl.innerHTML = `
            <div class="flex items-center justify-center p-4">
                <div class="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-[#4A7C3A]"></div>
                <span class="ml-2 text-gray-600">Decrypting...</span>
            </div>
        `;

        // Here you would add the actual decryption logic
        // For now, we'll just set the image source directly
        containerEl.innerHTML = `
            <img src="${mediaUrl}" alt="Decrypted content" class="max-w-full h-auto rounded-lg border border-[#D4E89A]">
        `;
    } catch (error) {
        console.error('Error in decryptAndRenderImage:', error);
        containerEl.innerHTML = `
            <div class="text-red-600 p-2 bg-red-100 rounded">
                Failed to load media: ${error.message}
            </div>
        `;
    }
}

class ChatManager {
    constructor(threadId, userId) {
        this.threadId = threadId;
        this.userId = String(userId);  // Ensure userId is always a string for comparison
        this.socket = null;
        this.connected = false;
        this.messageQueue = [];
        this.typingUsers = new Set();
        this.typingTimer = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.mediaKeys = {};
        this.reconnectTimeout = null;
        this.connectionTimeout = null;
        this.reconnecting = false;
        this.seenMessageIds = new Set();  // Track seen messages to prevent duplicates
    }

    // Connect to WebSocket
    connect(token) {
        // Prevent duplicate connections
        if (this.socket && (this.socket.readyState === WebSocket.CONNECTING || this.socket.readyState === WebSocket.OPEN)) {
            console.log('⚠️ WebSocket already connected or connecting, skipping...');
            return;
        }

        // Close existing connection if any
        if (this.socket) {
            console.log('Closing existing WebSocket connection...');
            this.socket.close();
        }

        // Create WebSocket connection
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/ws/chat/${this.threadId}/?token=${token}`;

        console.log('Attempting WebSocket connection to:', wsUrl.replace(token, token.substring(0, 10) + '...'));

        try {
            this.socket = new WebSocket(wsUrl);
            this.setupEventListeners(token);
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.updateConnectionStatus(false);
            this.scheduleReconnect(token);
        }
    }

    setupEventListeners(token) {
        if (!this.socket) return;

        this.socket.onopen = (event) => {
            console.log('✅ WebSocket connection established!');
            this.connected = true;
            this.reconnectAttempts = 0;
            this.processMessageQueue();
            this.updateConnectionStatus(true);
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('📨 WebSocket message received:', data);
                this.handleIncomingMessage(data);
            } catch (error) {
                console.error('❌ Error parsing WebSocket message:', error);
                console.error('Raw message data:', event.data);
            }
        };

        this.socket.onclose = (event) => {
            console.log('⚠️ WebSocket connection closed');
            console.log('Close code:', event.code, 'Reason:', event.reason || 'No reason provided');
            this.connected = false;
            this.updateConnectionStatus(false);
            this.scheduleReconnect(token);
        };

        this.socket.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            this.connected = false;
            this.updateConnectionStatus(false);
        };
    }

    processMessageQueue() {
        while (this.messageQueue.length > 0 && this.connected) {
            const message = this.messageQueue.shift();
            this.sendMessage(message);
        }
    }

    scheduleReconnect(token) {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached. Giving up.');
            return;
        }

        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        this.reconnectAttempts++;

        console.log(`Will attempt to reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

        this.reconnectTimeout = setTimeout(() => {
            if (!this.connected) {
                console.log('Attempting to reconnect...');
                this.connect(token);
            }
        }, delay);
    }

    sendMessage(message) {
        if (!this.connected) {
            console.log('Queueing message (not connected):', message);
            this.messageQueue.push(message);
            return false;
        }

        try {
            this.socket.send(JSON.stringify(message));
            console.log('📤 Sent message:', message);
            return true;
        } catch (error) {
            console.error('Error sending message:', error);
            this.messageQueue.unshift(message);
            return false;
        }
    }

    sendTextMessage(text) {
        console.log('📝 Sending text message:', text);

        // Display message locally immediately for sender
        const localMessage = {
            type: 'message.created',
            sender_id: this.userId,
            sender_name: 'You',
            content: text,
            timestamp: new Date().toISOString(),
            has_media: false
        };
        this.addMessageToChat(localMessage);

        // Send to other participant via WebSocket
        return this.sendMessage({
            type: 'message_new',
            text: text,
            thread_id: this.threadId,
            sender: this.userId
        });
    }

    sendTypingStatus(isTyping) {
        return this.sendMessage({
            type: isTyping ? 'typing_start' : 'typing_stop',
            thread_id: this.threadId,
            user: this.userId
        });
    }

    handleIncomingMessage(data) {
        try {
            console.log('📨 Received message:', data);
            const messageType = data.type || 'unknown';

            switch (messageType) {
                case 'message_new':
                    this.handleNewMessage(data);
                    break;
                case 'media_ack':
                    console.log('✅ Media upload acknowledged:', data);
                    // Media acknowledgment - just log it, the image will appear via message_new
                    break;
                case 'typing_start':
                    this.handleTypingStart(data);
                    break;
                case 'typing_stop':
                    this.handleTypingStop(data);
                    break;
                default:
                    console.log('Unhandled message type:', messageType, data);
            }
        } catch (error) {
            console.error('❌ Error handling incoming message:', error);
        }
    }

    handleNewMessage(data) {
        // Check for duplicate messages using message ID
        const messageId = data.id || data.message_id;
        if (messageId && this.seenMessageIds.has(messageId)) {
            console.log('⚠️ Duplicate message detected, skipping:', messageId);
            return;
        }

        // Add to seen messages
        if (messageId) {
            this.seenMessageIds.add(messageId);
            // Keep only last 100 message IDs to prevent memory leak
            if (this.seenMessageIds.size > 100) {
                const firstId = this.seenMessageIds.values().next().value;
                this.seenMessageIds.delete(firstId);
            }
        }

        // Convert sender to string for comparison (backend sends integer, userId is string)
        const senderId = String(data.sender || data.sender_id);
        if (senderId === this.userId) {
            console.log('Skipping own message from sender:', senderId);
            return;
        }
        
        console.log('📥 Processing incoming message from sender:', senderId, 'has_media:', data.has_media, 'media_url:', data.media_url);

        const message = {
            type: 'message.created',
            sender_id: data.sender || data.sender_id,
            sender_name: data.sender_name || 'User',
            content: data.text || data.content || '',
            timestamp: data.timestamp || data.created_at || new Date().toISOString(),
            has_media: data.has_media || data.media_type === 'image' || data.media?.type === 'image',  // Use has_media from backend!
            media_id: data.media_id || data.media?.id,
            media_mime: data.media_type || data.media?.type,
            media_url: data.media_url || data.media?.url,
            thumbnail_url: data.thumbnail_url || data.media?.thumbnail_url,
            file_name: data.file_name || data.media?.file_name,
            media_nonce_b64: data.iv || data.media?.iv,
            wrapped_keys: data.wrapped_keys || data.media?.wrapped_keys
        };

        this.addMessageToChat(message);
    }

    handleTypingStart(data) {
        if (data.user !== this.userId) {
            this.showTypingIndicator(data.user);
        }
    }

    handleTypingStop(data) {
        if (data.user !== this.userId) {
            this.hideTypingIndicator(data.user);
        }
    }

    addMessageToChat(message) {
        console.log('📩 Adding message to chat:', message);
        const chatContainer = document.getElementById('chat-messages');
        if (!chatContainer) {
            console.error('Chat container not found');
            return;
        }

        const noMessagesPlaceholder = chatContainer.querySelector('.no-messages');
        if (noMessagesPlaceholder) {
            noMessagesPlaceholder.remove();
        }

        const messageEl = this.createMessageElement(message);
        chatContainer.appendChild(messageEl);
        messageEl.scrollIntoView({ behavior: 'smooth' });
    }

    createMessageElement(message) {
        const isCurrentUser = String(message.sender_id) === this.userId;
        const messageEl = document.createElement('div');
        messageEl.className = `message-row ${isCurrentUser ? 'sent' : 'received'}`;
        
        // Get initials for avatar
        const senderName = message.sender_name || (isCurrentUser ? 'You' : 'User');
        const initials = senderName.charAt(0).toUpperCase();
        
        // Format time
        const time = new Date(message.timestamp).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });

        const messageContent = `
            <div class="message-avatar">${initials}</div>
            <div class="message-group">
                <div class="message-sender">${isCurrentUser ? 'You' : senderName}, ${time}</div>
                <div class="message-bubble">
                    <div class="message-content">
                        ${message.content ? `<p>${message.content}</p>` : ''}
                        ${this.createMediaContent(message)}
                    </div>
                </div>
            </div>
        `;

        messageEl.innerHTML = messageContent;
        return messageEl;
    }

    createMediaContent(message) {
        console.log('🖼️ createMediaContent called with:', {
            has_media: message.has_media,
            media_url: message.media_url,
            media_id: message.media_id
        });

        if (!message.has_media || !message.media_url) {
            console.log('⚠️ Skipping media - missing has_media or media_url');
            return '';
        }

        console.log('🖼️ Processing media message:', message);
        console.log('  media_mime:', message.media_mime);

        const isCurrentUser = String(message.sender_id) === this.userId;

        // Show image if media_mime starts with 'image' (handles both 'image/jpeg' and 'image')
        // OR if it's not set but we have a media_url (fallback)
        const isImage = message.media_mime?.startsWith('image') || !message.media_mime;

        console.log('🖼️ isImage check result:', isImage);
        
        if (isImage) {
            // Generate a unique ID for this image element
            const uniqueId = message.media_id || `img-${Date.now()}`;
            const displayUrl = message.thumbnail_url || message.media_url;
            const fullUrl = message.media_url;
            
            console.log('🖼️ Rendering image with URL:', displayUrl);
            console.log('🖼️ Full URL:', fullUrl);
            
            if (message.media_nonce_b64 && message.wrapped_keys) {
                // Encrypted image - needs decryption
                return `
                    <div class="media-container my-2 relative group">
                        <div class="media-placeholder" id="media-${uniqueId}">
                            <div class="animate-pulse flex items-center justify-center bg-gray-200 rounded-lg w-full h-32">
                                <span class="text-gray-500">Decrypting image...</span>
                            </div>
                        </div>
                        ${isCurrentUser ? `
                            <button onclick="window.chatManager.deleteImage('${uniqueId}')" 
                                    class="absolute top-1 right-1 bg-red-600 hover:bg-red-700 text-white rounded-full w-6 h-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 font-bold text-sm shadow-lg"
                                    title="Delete image">
                                ×
                            </button>
                        ` : ''}
                        ${message.content ? `<p class="text-sm mt-2">${message.content}</p>` : ''}
                    </div>
                `;
            } else {
                // Unencrypted image - display directly with analyze button
                return `
                    <div class="my-2" style="position: relative;">
                        <img src="${displayUrl}" 
                             alt="${message.file_name || 'Image'}" 
                             class="max-w-full h-auto rounded-lg border border-[#D4E89A] cursor-pointer hover:opacity-90 transition-opacity"
                             style="max-height: 300px; min-width: 150px; min-height: 150px; object-fit: cover; display: block;"
                             onerror="this.onerror=null; this.src='${fullUrl}'; console.log('Image load error, trying full URL:', '${fullUrl}');"
                             onclick="openImageModal('${fullUrl}', '${uniqueId}')">
                        
                        <!-- Analyze button below image -->
                        <button onclick="event.stopPropagation(); analyzeImageWithAI('${fullUrl}', '${uniqueId}')" 
                                class="mt-2 w-full bg-gradient-to-r from-[#C5D86D] to-[#B5C95A] hover:from-[#B5C95A] hover:to-[#A5B94A] text-[#1A3316] px-3 py-1.5 rounded-lg text-sm font-semibold shadow flex items-center justify-center gap-1"
                                title="Analyze image with AI">
                            <i class="fas fa-robot"></i> Analyze with AI
                        </button>
                        
                        ${isCurrentUser ? `
                            <button onclick="event.stopPropagation(); window.chatManager.deleteImage('${uniqueId}')" 
                                    class="absolute top-2 right-2 bg-red-600 hover:bg-red-700 text-white rounded-full w-6 h-6 flex items-center justify-center font-bold shadow-lg"
                                    style="position: absolute; top: 8px; right: 8px;"
                                    title="Delete image">
                                ×
                            </button>
                        ` : ''}
                    </div>
                `;
            }
        }

        return '';
    }

    updateConnectionStatus(isConnected) {
        const statusEl = document.getElementById('connection-status');
        if (!statusEl) return;

        if (isConnected) {
            statusEl.innerHTML = '🟢 Connected';
            statusEl.className = 'text-green-500 text-sm';
        } else {
            statusEl.innerHTML = '🔴 Disconnected';
            statusEl.className = 'text-red-500 text-sm';
        }
    }

    showTypingIndicator(userId) {
        if (userId === this.userId) return;

        this.typingUsers.add(userId);
        this.updateTypingIndicator();

        if (this.typingTimer) {
            clearTimeout(this.typingTimer);
        }

        this.typingTimer = setTimeout(() => {
            this.hideTypingIndicator(userId);
        }, 5000);
    }

    hideTypingIndicator(userId) {
        if (userId) {
            this.typingUsers.delete(userId);
        } else {
            this.typingUsers.clear();
        }
        this.updateTypingIndicator();
    }

    updateTypingIndicator() {
        const typingContainer = document.getElementById('typing-indicator');
        if (!typingContainer) return;

        const typingCount = this.typingUsers.size;

        if (typingCount > 0) {
            const names = Array.from(this.typingUsers).join(', ');
            typingContainer.textContent = `${names} ${typingCount > 1 ? 'are' : 'is'} typing...`;
            typingContainer.style.display = 'block';
        } else {
            typingContainer.style.display = 'none';
        }
    }

    deleteImage(mediaId) {
        // Confirm deletion
        if (!confirm('Are you sure you want to delete this image?')) {
            return;
        }

        console.log('Deleting image:', mediaId);

        // Send delete message through WebSocket
        this.sendMessage({
            type: 'delete_media',
            media_id: mediaId,
            thread_id: this.threadId,
            sender: this.userId
        });

        // Remove image from UI immediately for better UX
        const imageContainer = document.querySelector(`#media-${mediaId}`);
        if (imageContainer) {
            const mediaParent = imageContainer.closest('.media-container') || imageContainer.closest('.my-2');
            if (mediaParent) {
                mediaParent.innerHTML = '<p class="text-xs text-gray-500 italic">Image deleted</p>';
            }
        }
    }
}

// Initialize chat when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const threadId = document.getElementById('thread-id')?.value;
    const userId = document.getElementById('current-user-id')?.value;
    const token = document.getElementById('jwt-token')?.value;

    if (!threadId || !userId || !token) {
        console.error('Missing required elements for chat initialization');
        return;
    }

    // Initialize chat manager
    window.chatManager = new ChatManager(threadId, userId);
    window.chatManager.connect(token);

    // Set up message form submission
    const messageForm = document.getElementById('message-form');
    if (messageForm) {
        messageForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const input = messageForm.querySelector('input[type="text"]');
            const message = input.value.trim();

            if (message) {
                window.chatManager.sendMessage({
                    type: 'message_new',
                    text: message,
                    thread_id: threadId,
                    sender: userId
                });

                // Clear input
                input.value = '';
            }
        });
    }

    // Set up typing indicator
    const messageInput = document.querySelector('input[type="text"]');
    if (messageInput) {
        let typingTimeout;

        messageInput.addEventListener('input', () => {
            // Send typing start
            window.chatManager.sendMessage({
                type: 'typing_start',
                thread_id: threadId,
                user: userId
            });

            // Clear previous timeout
            if (typingTimeout) {
                clearTimeout(typingTimeout);
            }

            // Set timeout to send typing stop after 2 seconds of inactivity
            typingTimeout = setTimeout(() => {
                window.chatManager.sendMessage({
                    type: 'typing_stop',
                    thread_id: threadId,
                    user: userId
                });
            }, 2000);
        });
    }
});

// Image Modal Functions
function openImageModal(imageUrl, mediaId) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('image-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'image-modal';
        modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-90 hidden opacity-0 transition-opacity duration-300';
        modal.innerHTML = `
            <div class="relative max-w-4xl max-h-screen w-full h-full flex items-center justify-center p-4">
                <button onclick="closeImageModal()" class="absolute top-4 right-4 text-white text-4xl hover:text-gray-300 z-50 focus:outline-none">&times;</button>
                <img id="modal-image" src="" alt="Full size" class="max-w-full max-h-full object-contain rounded-lg shadow-2xl transform scale-95 transition-transform duration-300">
                <div id="modal-loader" class="absolute inset-0 flex items-center justify-center">
                    <div class="animate-spin rounded-full h-12 w-12 border-t-4 border-b-4 border-white"></div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Close on background click
        modal.addEventListener('click', (e) => {
            if (e.target === modal || e.target.closest('.relative') === e.target) {
                closeImageModal();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
                closeImageModal();
            }
        });
    }

    const modalImg = document.getElementById('modal-image');
    const modalLoader = document.getElementById('modal-loader');

    // Reset state
    modalImg.style.display = 'none';
    modalLoader.style.display = 'flex';
    modalImg.src = imageUrl;

    // Show modal
    modal.classList.remove('hidden');
    // Trigger reflow
    void modal.offsetWidth;
    modal.classList.remove('opacity-0');

    // Handle image load
    modalImg.onload = function () {
        modalLoader.style.display = 'none';
        modalImg.style.display = 'block';
        modalImg.classList.remove('scale-95');
        modalImg.classList.add('scale-100');
    };
}

function closeImageModal() {
    const modal = document.getElementById('image-modal');
    if (modal) {
        modal.classList.add('opacity-0');
        const modalImg = document.getElementById('modal-image');
        if (modalImg) {
            modalImg.classList.remove('scale-100');
            modalImg.classList.add('scale-95');
        }

        setTimeout(() => {
            modal.classList.add('hidden');
            if (modalImg) modalImg.src = '';
        }, 300);
    }
}

// Analyze image with AI
function analyzeImageWithAI(imageUrl, mediaId) {
    console.log('🤖 Analyzing image with AI:', imageUrl);
    
    // Switch to AI panel on mobile
    if (window.innerWidth <= 1024) {
        const aiTab = document.querySelectorAll('.mobile-tab')[1];
        if (aiTab) aiTab.click();
    }
    
    // Show loading message in AI panel
    const aiMessages = document.getElementById('ai-messages');
    if (!aiMessages) {
        console.error('AI messages container not found');
        return;
    }
    
    // Add user message showing the image being analyzed
    const userMsgDiv = document.createElement('div');
    userMsgDiv.className = 'message-bubble sent';
    userMsgDiv.innerHTML = `
        <div class="message-content" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <p class="mb-2">Please analyze this image:</p>
            <img src="${imageUrl}" alt="Image to analyze" class="max-w-full h-auto rounded-lg" style="max-height: 150px;">
        </div>
        <div class="message-meta" style="justify-content: flex-end;">
            <span>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </div>
    `;
    aiMessages.appendChild(userMsgDiv);
    
    // Add loading indicator
    const loadingId = 'ai-loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.className = 'ai-message';
    loadingDiv.innerHTML = `
        <div class="ai-message-header">
            <i class="fas fa-robot"></i>
            AI Assistant
        </div>
        <div class="ai-message-text">
            <div class="flex items-center gap-2">
                <div class="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-[#2D5A27]"></div>
                <span>Analyzing image...</span>
            </div>
        </div>
    `;
    aiMessages.appendChild(loadingDiv);
    aiMessages.scrollTop = aiMessages.scrollHeight;
    
    // Get the full image URL
    const fullImageUrl = imageUrl.startsWith('http') ? imageUrl : window.location.origin + imageUrl;
    
    // Call AI analysis endpoint
    const token = document.getElementById('jwt-token')?.value;
    const threadId = document.getElementById('thread-id')?.value;
    
    // Get CSRF token from cookie
    const csrfToken = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];
    
    fetch('/api/ai/analyze-image/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            image_url: fullImageUrl,
            thread_id: threadId,
            media_id: mediaId
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        // Remove loading indicator
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();
        
        // Add AI response
        const responseDiv = document.createElement('div');
        responseDiv.className = 'ai-message';
        responseDiv.innerHTML = `
            <div class="ai-message-header">
                <i class="fas fa-robot"></i>
                AI Assistant
            </div>
            <div class="ai-message-text">
                ${data.analysis || data.message || 'Analysis complete.'}
            </div>
        `;
        aiMessages.appendChild(responseDiv);
        aiMessages.scrollTop = aiMessages.scrollHeight;
    })
    .catch(error => {
        console.error('Error analyzing image:', error);
        
        // Remove loading indicator
        const loadingEl = document.getElementById(loadingId);
        if (loadingEl) loadingEl.remove();
        
        // Show error message
        const errorDiv = document.createElement('div');
        errorDiv.className = 'ai-message';
        errorDiv.innerHTML = `
            <div class="ai-message-header">
                <i class="fas fa-robot"></i>
                AI Assistant
            </div>
            <div class="ai-message-text text-red-600">
                Sorry, I couldn't analyze this image. Error: ${error.message}
            </div>
        `;
        aiMessages.appendChild(errorDiv);
        aiMessages.scrollTop = aiMessages.scrollHeight;
    });
}
