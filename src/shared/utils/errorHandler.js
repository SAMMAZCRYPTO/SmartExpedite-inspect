/**
 * Centralized Error Handler
 * 
 * Provides consistent error handling across the application with user-friendly messages
 * and optional error reporting to monitoring services.
 * 
 * @module errorHandler
 */

/**
 * Handles database errors with user-friendly messaging
 * 
 * WHY: Provides consistent error handling across the app, preventing duplicate
 * error handling code and ensuring users get helpful messages instead of technical errors.
 * 
 * @param {Error} error - The error object from database operation
 * @param {string} context - Where the error occurred (e.g., 'fetchInspections', 'createProject')
 * @param {Object} options - Additional options
 * @param {Function} [options.onError] - Callback to execute after error is handled
 * @param {boolean} [options.silent=false] - If true, doesn't show toast notification
 * @param {Function} [options.toast] - Toast notification function (optional, uses window.toast if available)
 * 
 * @returns {string} User-friendly error message
 * 
 * @example
 * try {
 *   await updateInspection(id, data);
 * } catch (error) {
 *   handleDatabaseError(error, 'updateInspection', {
 *     onError: () => refetchInspections()
 *   });
 * }
 */
export function handleDatabaseError(error, context, options = {}) {
    const { onError, silent = false, toast } = options;

    // Log error for debugging
    console.error(`[${context}] Database Error:`, {
        message: error.message,
        code: error.code,
        details: error.details,
        hint: error.hint,
    });

    // Send to monitoring service if available (e.g., Sentry, LogRocket)
    if (typeof window !== 'undefined' && window.Sentry) {
        window.Sentry.captureException(error, {
            tags: { context, type: 'database_error' },
            extra: {
                code: error.code,
                details: error.details,
            },
        });
    }

    // Get user-friendly message
    const userMessage = getUserFriendlyMessage(error);

    // Show toast notification if not silent
    if (!silent) {
        const toastFn = toast || (typeof window !== 'undefined' && window.toast);
        if (toastFn && typeof toastFn.error === 'function') {
            toastFn.error(userMessage);
        } else {
            console.warn('Toast notification not available');
        }
    }

    // Execute callback if provided
    if (onError && typeof onError === 'function') {
        onError();
    }

    return userMessage;
}

/**
 * Converts technical database errors to user-friendly messages
 * 
 * @param {Error} error - Database error
 * @returns {string} User-friendly error message
 */
function getUserFriendlyMessage(error) {
    const errorMessage = error.message?.toLowerCase() || '';

    // Check for common error patterns in message
    if (errorMessage.includes('timeout')) {
        return 'Request timed out. Please check your connection and try again.';
    }

    if (errorMessage.includes('network') || errorMessage.includes('fetch') || errorMessage.includes('failed to fetch')) {
        return 'Network error. Please check your internet connection and ensure the backend is running.';
    }

    if (errorMessage.includes('permission') || errorMessage.includes('unauthorized') || errorMessage.includes('forbidden')) {
        return 'You do not have permission to perform this action.';
    }

    if (errorMessage.includes('duplicate') || errorMessage.includes('already exists')) {
        return 'This record already exists.';
    }

    if (errorMessage.includes('not found') || errorMessage.includes('404')) {
        return 'Record not found. It may have been deleted or you may not have access.';
    }

    // Generic fallback
    return error.message || 'An unexpected error occurred. Please try again or contact support if the problem persists.';
}

/**
 * Handles API/network errors (non-database)
 * 
 * @param {Error} error - API error
 * @param {string} context - Where the error occurred
 * @returns {string} User-friendly error message
 */
export function handleAPIError(error, context) {
    console.error(`[${context}] API Error:`, error);

    if (error.response) {
        // Server responded with error status
        const status = error.response.status;

        switch (status) {
            case 400:
                return 'Invalid request. Please check your input.';
            case 401:
                return 'Session expired. Please log in again.';
            case 403:
                return 'You do not have permission to access this resource.';
            case 404:
                return 'Resource not found.';
            case 429:
                return 'Too many requests. Please wait a moment and try again.';
            case 500:
                return 'Server error. Please try again later.';
            case 503:
                return 'Service temporarily unavailable. Please try again later.';
            default:
                return `Server error (${status}). Please try again.`;
        }
    }

    if (error.request) {
        // Request made but no response
        return 'No response from server. Please check your connection.';
    }

    // Something else went wrong
    return 'An unexpected error occurred. Please try again.';
}

/**
 * Validates that required environment variables are set
 * 
 * WHY: Catch configuration errors early in development before they cause
 * runtime failures in production.
 * 
 * @param {Array<string>} requiredVars - Array of required env var names
 * @throws {Error} If any required variable is missing
 */
export function validateEnvironmentVariables(requiredVars) {
    const missing = requiredVars.filter(varName => !import.meta.env[varName]);

    if (missing.length > 0) {
        throw new Error(
            `Missing required environment variables: ${missing.join(', ')}. ` +
            'Please check your .env file and ensure all required variables are set.'
        );
    }
}

/**
 * Safe JSON parse with error handling
 * 
 * @param {string} jsonString - JSON string to parse
 * @param {any} fallback - Fallback value if parse fails
 * @returns {any} Parsed object or fallback
 */
export function safeJSONParse(jsonString, fallback = null) {
    try {
        return JSON.parse(jsonString);
    } catch (error) {
        console.warn('JSON parse error:', error);
        return fallback;
    }
}
