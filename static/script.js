// CUI Campus Chatbot - Frontend JavaScript

let isTyping = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chatForm');
    const messageInput = document.getElementById('messageInput');
    
    chatForm.addEventListener('submit', function(e) {
        e.preventDefault();
        sendMessage();
    });
    
    // Focus on input
    messageInput.focus();
    
    // Check system status
    checkStatus();
});

// Send message to chatbot
async function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (!message || isTyping) return;
    
    // Clear input
    messageInput.value = '';
    
    // Hide welcome section
    const welcomeSection = document.getElementById('welcomeSection');
    if (welcomeSection) {
        welcomeSection.style.display = 'none';
    }
    
    // Add user message
    addMessage(message, 'user');
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ message: message })
        });
        
        const data = await response.json();
        
        // Hide typing indicator
        hideTypingIndicator();
        
        if (data.success) {
            // Add bot response
            addMessage(data.answer, 'bot', data.sources, data.categories);
        } else {
            addMessage('Sorry, I encountered an error. Please try again.', 'bot');
        }
    } catch (error) {
        console.error('Error:', error);
        hideTypingIndicator();
        addMessage('Sorry, I couldn\'t connect to the server. Please check your connection.', 'bot');
    }
    
    // Focus back on input
    messageInput.focus();
}

// Add message to chat
// Toggle showing metadata badges (sources/categories)
const SHOW_METADATA = false; // set true to re-enable

function addMessage(text, sender, sources = [], categories = []) {
    const chatContainer = document.getElementById('chatContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    
    if (sender === 'user') {
        messageDiv.innerHTML = `
            <div class="flex justify-end mb-4">
                <div class="max-w-3xl">
                    <div class="bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-2xl rounded-tr-none px-6 py-4 shadow-lg">
                        <p class="text-sm md:text-base">${escapeHtml(text)}</p>
                    </div>
                </div>
            </div>
        `;
    } else {
        let sourcesHtml = '';
        if (SHOW_METADATA && sources && sources.length > 0) {
            sourcesHtml = `
                <div class="mt-3 flex flex-wrap gap-2">
                    <span class="text-xs text-gray-500">
                        <i class="fas fa-book mr-1"></i>Sources:
                    </span>
                    ${sources.map(source => `<span class="badge source-badge">${escapeHtml(source)}</span>`).join('')}
                </div>
            `;
        }
        
        let categoriesHtml = '';
        if (SHOW_METADATA && categories && categories.length > 0) {
            categoriesHtml = `
                <div class="mt-2 flex flex-wrap gap-2">
                    <span class="text-xs text-gray-500">
                        <i class="fas fa-tag mr-1"></i>Categories:
                    </span>
                    ${categories.map(cat => `<span class="badge category-badge">${escapeHtml(cat)}</span>`).join('')}
                </div>
            `;
        }
        
        messageDiv.innerHTML = `
            <div class="flex justify-start mb-4">
                <div class="max-w-3xl">
                    <div class="flex items-start space-x-3">
                        <div class="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center flex-shrink-0 mt-1">
                            <i class="fas fa-robot text-white"></i>
                        </div>
                        <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-none px-6 py-4 shadow-lg flex-1">
                            <p class="text-sm md:text-base text-gray-800 whitespace-pre-wrap">${escapeHtml(text)}</p>
                            ${sourcesHtml}
                            ${categoriesHtml}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

// Show typing indicator
function showTypingIndicator() {
    isTyping = true;
    const chatContainer = document.getElementById('chatContainer');
    const typingDiv = document.createElement('div');
    typingDiv.id = 'typingIndicator';
    typingDiv.className = 'message';
    typingDiv.innerHTML = `
        <div class="flex justify-start mb-4">
            <div class="flex items-start space-x-3">
                <div class="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-white"></i>
                </div>
                <div class="bg-white border border-gray-200 rounded-2xl rounded-tl-none shadow-lg">
                    <div class="typing-indicator">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            </div>
        </div>
    `;
    chatContainer.appendChild(typingDiv);
    scrollToBottom();
}

// Hide typing indicator
function hideTypingIndicator() {
    isTyping = false;
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Send suggested question
function sendSuggestion(question) {
    const messageInput = document.getElementById('messageInput');
    messageInput.value = question;
    sendMessage();
}

// Clear chat history
async function clearChat() {
    if (!confirm('Are you sure you want to clear the chat history?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Clear chat container
            const chatContainer = document.getElementById('chatContainer');
            chatContainer.innerHTML = '';
            
            // Show welcome section
            const welcomeSection = document.getElementById('welcomeSection');
            if (welcomeSection) {
                welcomeSection.style.display = 'block';
            }
            
            // Show success notification
            showNotification('Chat history cleared!', 'success');
        }
    } catch (error) {
        console.error('Error clearing chat:', error);
        showNotification('Failed to clear chat history', 'error');
    }
}

// Check system status
async function checkStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (!data.success) {
            showNotification('System is offline. Please refresh the page.', 'error');
        }
    } catch (error) {
        console.error('Status check failed:', error);
    }
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-6 py-4 rounded-lg shadow-lg z-50 animate-fade-in ${
        type === 'success' ? 'bg-green-500' : 
        type === 'error' ? 'bg-red-500' : 
        'bg-blue-500'
    } text-white`;
    notification.innerHTML = `
        <div class="flex items-center space-x-2">
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Scroll to bottom of chat
function scrollToBottom() {
    const chatContainer = document.getElementById('chatContainer');
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Add keyboard shortcuts
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + K to focus on input
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        document.getElementById('messageInput').focus();
    }
    
    // Escape to clear input
    if (e.key === 'Escape') {
        document.getElementById('messageInput').value = '';
        document.getElementById('messageInput').blur();
    }
});

// Auto-resize textarea on input (if we switch to textarea later)
function autoResize(element) {
    element.style.height = 'auto';
    element.style.height = element.scrollHeight + 'px';
}
