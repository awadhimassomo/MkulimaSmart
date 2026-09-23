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
        this.userId = userId;
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
    }

    // Connect to WebSocket
    connect(token) {
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

    handleIncomingMessage(data) {
        try {
            console.log('📨 Received message:', data);
            const messageType = data.type || 'unknown';
            
            switch (messageType) {
                case 'message_new':
                    this.handleNewMessage(data);
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
        if (data.sender === this.userId) {
            console.log('Skipping own message');
            return;
        }

        const message = {
            type: 'message.created',
            sender_id: data.sender,
            sender_name: data.sender_name || 'User',
            content: data.text || data.content || '',
            timestamp: data.timestamp || new Date().toISOString(),
            has_media: data.media_type === 'image' || data.media?.type === 'image',
            media_id: data.media_id || data.media?.id,
            media_mime: data.media_type || data.media?.type,
            media_url: data.media_url || data.media?.url,
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
        const isCurrentUser = message.sender_id === this.userId;
        const messageEl = document.createElement('div');
        messageEl.className = `flex ${isCurrentUser ? 'justify-end' : 'justify-start'} mb-4`;
        
        const messageContent = `
            <div class="max-w-xs md:max-w-md lg:max-w-lg xl:max-w-xl rounded-lg px-4 py-2 ${
                isCurrentUser 
                    ? 'bg-gradient-to-r from-[#2D5A27] to-[#4A7C3A] text-white rounded-br-none' 
                    : 'bg-gray-200 text-gray-800 rounded-bl-none'
            }">
                ${message.content ? `<p class="mb-1">${message.content}</p>` : ''}
                ${this.createMediaContent(message)}
                <p class="text-xs opacity-75 text-right mt-1">
                    ${new Date(message.timestamp).toLocaleTimeString()}
                </p>
            </div>
        `;
        
        messageEl.innerHTML = messageContent;
        return messageEl;
    }

    createMediaContent(message) {
        if (!message.has_media || !message.media_url) return '';

        console.log('🖼️ Processing media message:', message);
        
        if (message.media_mime?.startsWith('image/')) {
            if (message.media_nonce_b64 && message.wrapped_keys) {
                return `
                    <div class="media-container my-2">
                        <div class="media-placeholder" id="media-${message.media_id}">
                            <div class="animate-pulse flex items-center justify-center bg-gray-200 rounded-lg w-full h-32">
                                <span class="text-gray-500">Decrypting image...</span>
                            </div>
                        </div>
                        ${message.content ? `<p class="text-sm mt-2">${message.content}</p>` : ''}
                    </div>
                `;
            } else {
                return `
                    <div class="my-2">
                        <img src="${message.media_url}" 
                             alt="${message.file_name || 'Image'}" 
                             class="max-w-full h-auto rounded-lg border border-[#D4E89A]">
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
