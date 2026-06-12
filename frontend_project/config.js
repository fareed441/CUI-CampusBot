/**
 * Frontend Configuration
 * Handles API endpoints for different environments
 */

const CONFIG = {
    // Auto-detect: use same host as frontend, port 8000 for API
    API_BASE_URL: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://localhost:8000'
        : `http://${window.location.hostname}:8000`,

    // API Endpoints
    ENDPOINTS: {
        LOGIN: '/api/auth/login',
        REGISTER: '/api/auth/register',
        CHAT: '/api/chat',
        FEEDBACK: '/api/feedback',
        DOCUMENTS: '/api/documents',
        TIMETABLE: '/api/timetable'
    }
};

/**
 * Helper function to make API calls
 * @param {string} endpoint - API endpoint path
 * @param {object} options - Fetch options
 * @returns {Promise} - Fetch promise
 */
async function apiCall(endpoint, options = {}) {
    const url = `${CONFIG.API_BASE_URL}${endpoint}`;

    // Set default headers
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    // Add auth token if exists
    const token = localStorage.getItem('access_token');
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'API Error');
        }

        return response.json();
    } catch (error) {
        console.error('API Call Failed:', error);
        throw error;
    }
}

// Export for module systems (optional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { CONFIG, apiCall };
}
