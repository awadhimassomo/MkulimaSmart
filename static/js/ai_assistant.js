/**
 * AI Assistant Integration for Split-Screen Chat Interface
 * Provides real-time AI assistance for government officers
 * Brand Colors: Mkulima Smart (#2D5A27, #C5D86D)
 */

class AIAssistant {
    constructor(threadId) {
        this.threadId = threadId;
        this.baseUrl = window.location.origin;
        this.loadingId = null;
    }

    async askQuestion(question) {
        try {
            this.addMessageToUI(question, 'user');
            this.showLoading();

            const csrfToken = this.getCookie('csrftoken');
            const response = await fetch(`${this.baseUrl}/gova-pp/api/ai/chat/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    question: question,
                    thread_id: this.threadId
                })
            });

            const data = await response.json();
            this.hideLoading();

            if (data.success) {
                this.addMessageToUI(data.response, 'ai');
            } else {
                this.addMessageToUI('Sorry, I encountered an error. Please try again.', 'ai');
            }
        } catch (error) {
            console.error('AI Assistant Error:', error);
            this.hideLoading();
            this.addMessageToUI('Sorry, I could not process your request. Please try again.', 'ai');
        }
    }

    addMessageToUI(text, sender) {
        const aiMessages = document.getElementById('ai-messages');
        if (!aiMessages) return;

        const messageDiv = document.createElement('div');

        if (sender === 'user') {
            messageDiv.className = 'message-bubble sent';
            messageDiv.innerHTML = `
                <div class="message-content" style="background: linear-gradient(135deg, #C5D86D 0%, #B5C95A 100%); color: #1A3316;">
                   ${this.escapeHtml(text)}
                </div>
                <div class="message-meta" style="justify-content: flex-end;">
                    <span>${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
            `;
        } else {
            messageDiv.className = 'ai-message';
            messageDiv.innerHTML = `
                <div class="ai-message-header">
                    <i class="fas fa-robot"></i>
                    AI Assistant
                </div>
                <div class="ai-message-text">
                    ${text}
                </div>
            `;
        }

        aiMessages.appendChild(messageDiv);
        aiMessages.scrollTop = aiMessages.scrollHeight;
    }

    showLoading() {
        this.loadingId = 'loading-' + Date.now();
        const aiMessages = document.getElementById('ai-messages');
        if (!aiMessages) return;

        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'ai-message';
        loadingDiv.id = this.loadingId;
        loadingDiv.innerHTML = `
            <div class="ai-message-header">
                <i class="fas fa-robot"></i>
                AI Assistant
            </div>
            <div class="ai-message-text">
                <div class="loading-spinner" style="width: 16px; height: 16px; display: inline-block; border: 2px solid rgba(197, 216, 109, 0.3); border-top-color: #C5D86D; border-radius: 50%; animation: spin 0.6s linear infinite;"></div>
                Thinking...
            </div>
        `;

        aiMessages.appendChild(loadingDiv);
        aiMessages.scrollTop = aiMessages.scrollHeight;
    }

    hideLoading() {
        if (this.loadingId) {
            const loadingElement = document.getElementById(this.loadingId);
            if (loadingElement) {
                loadingElement.remove();
            }
            this.loadingId = null;
        }
    }

    displaySuggestions(suggestions) {
        const suggestionsHtml = suggestions.map(s => `
            <div style="margin-bottom: 0.75rem; padding: 0.75rem; background: #f8faf5; border-left: 3px solid #C5D86D; border-radius: 8px; cursor: pointer;" onclick="copySuggestionToChat('${this.escapeHtml(s.text)}')">
                <div style="font-weight: 600; color: #2D5A27; margin-bottom: 0.25rem;">${s.title}</div>
                <div style="font-size: 0.875rem; color: #374151;">${this.escapeHtml(s.text)}</div>
            </div>
        `).join('');

        this.addMessageToUI(`
            <strong>Suggested Responses:</strong>
            <div style="margin-top: 0.5rem;">
                ${suggestionsHtml}
            </div>
            <em style="font-size: 0.875rem; color: #6b7280;">Click any suggestion to copy it to the customer chat.</em>
        `, 'ai');
    }

    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
}

// Global functions
function askAI(question) {
    if (window.aiAssistant) {
        const aiInput = document.getElementById('ai-input');
        if (aiInput) aiInput.value = question;
        window.aiAssistant.askQuestion(question);
    }
}

function copySuggestionToChat(text) {
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        messageInput.value = text;
        messageInput.focus();
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
        showToast('Response copied to chat input!', 'success');
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        padding: 1rem 1.5rem;
        background: ${type === 'success' ? '#10b981' : '#C5D86D'};
        color: ${type === 'success' ? 'white' : '#1A3316'};
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        z-index: 9999;
        animation: slideIn 0.3s ease-out;
        font-weight: 600;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const threadIdEl = document.getElementById('thread-id');

    if (threadIdEl) {
        const threadId = threadIdEl.value;
        window.aiAssistant = new AIAssistant(threadId);

        const aiSendButton = document.getElementById('ai-send-button');
        const aiInput = document.getElementById('ai-input');

        if (aiSendButton && aiInput) {
            aiSendButton.addEventListener('click', () => {
                const text = aiInput.value.trim();
                if (text) {
                    window.aiAssistant.askQuestion(text);
                    aiInput.value = '';
                    aiInput.style.height = 'auto';
                }
            });

            aiInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    aiSendButton.click();
                }
            });
        }
    }
});
