const TOKEN_KEY = 'inspectflow_access_token';
const SESSION_KEY = 'inspectflow_mock_session';

export const getApiOrigin = () => {
    const raw = import.meta.env.VITE_CSHARP_API_URL || '';
    if (!raw) return '';
    return raw.replace(/\/api\/?$/, '');
};

export const getApiBaseUrl = () => {
    return import.meta.env.VITE_CSHARP_API_URL || '/api';
};

export const getAccessToken = () => {
    try {
        return localStorage.getItem(TOKEN_KEY) || '';
    } catch {
        return '';
    }
};

export const setAccessToken = (token) => {
    try {
        if (token) {
            localStorage.setItem(TOKEN_KEY, token);
        } else {
            localStorage.removeItem(TOKEN_KEY);
        }
    } catch {}
};

export const clearAccessToken = () => {
    try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(SESSION_KEY);
        localStorage.removeItem('selected_project_id');
        if (window.sessionStorage) {
            sessionStorage.removeItem('if_auth_token');
            sessionStorage.removeItem('sx_user');
        }
    } catch {}
};

let _installed = false;

/**
 * Intercepts same-origin or backend API/Upload fetch calls to attach
 * the signed Bearer JWT and credentials cookie automatically.
 */
export const installAuthFetchInterceptor = () => {
    if (_installed || typeof window === 'undefined' || typeof window.fetch !== 'function') {
        return;
    }
    _installed = true;
    const origFetch = window.fetch.bind(window);
    const apiOrigin = getApiOrigin();

    window.fetch = (input, init = {}) => {
        try {
            const url = typeof input === 'string' ? input : input?.url || '';
            const isBackendApi =
                url.startsWith('/api') ||
                url.startsWith('/uploads') ||
                url.startsWith('/smartexpedit-app') ||
                (apiOrigin && url.startsWith(apiOrigin));

            if (isBackendApi) {
                const token = getAccessToken();
                const headers = new Headers(
                    init.headers || (typeof input !== 'string' && input?.headers) || undefined
                );
                if (token && !headers.has('Authorization')) {
                    headers.set('Authorization', `Bearer ${token}`);
                }
                const nextInit = {
                    ...init,
                    headers,
                    credentials: init.credentials || 'include',
                };
                return origFetch(input, nextInit);
            }
        } catch {
            // Fallback to unmodified fetch on parse anomalies
        }
        return origFetch(input, init);
    };
};
