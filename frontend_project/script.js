// Handle file upload name display in the login page
function showFileName() {
    const fileInput = document.getElementById('file-upload');
    const fileName = fileInput.files.length ? fileInput.files[0].name : 'No file chosen';
    document.getElementById('file-name').textContent = fileName;
}

// Handle chat functionality in chat.html
function sendMessage() {
    const input = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');

    // Send the message to chat window
    const message = document.createElement('div');
    message.classList.add('bg-green-100', 'p-2', 'rounded-md', 'mb-2');
    message.textContent = input.value;
    chatMessages.appendChild(message);

    // Clear input field
    input.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight; // Auto scroll to the latest message
}
