/**
 * Backend-Backed Authentication & Session Client for InspectFlow
 *
 * Uses FastAPI /api/v2/auth/* with real signed JWT tokens + HttpOnly cookies.
 * Supports AUTH_MODE=dev quick role switching during testing and transitions cleanly
 * to Microsoft Entra ID + Argon2/PBKDF2 MFA in AUTH_MODE=production.
 */
import {
    clearAccessToken,
    getAccessToken,
    getApiBaseUrl,
    setAccessToken,
} from '../authFetch';

const SESSION_KEY = 'inspectflow_mock_session';

const authBase = () => `${getApiBaseUrl()}/v2/auth`;

const readSession = () => {
    try {
        const raw = localStorage.getItem(SESSION_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
};

const writeSession = (user) => {
    try {
        if (user) {
            localStorage.setItem(SESSION_KEY, JSON.stringify(user));
        } else {
            localStorage.removeItem(SESSION_KEY);
        }
    } catch { }
};

const apiJson = async (url, options = {}) => {
    const token = getAccessToken();
    const headers = new Headers(options.headers || {});
    if (!headers.has('Content-Type') && options.body && !(options.body instanceof FormData)) {
        headers.set('Content-Type', 'application/json');
    }
    if (token && !headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    const resp = await fetch(url, {
        ...options,
        headers,
        credentials: 'include',
    });
    const text = await resp.text();
    let data = {};
    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        data = { detail: text };
    }
    if (!resp.ok) {
        const err = new Error(data.detail || data.message || `Request failed (${resp.status})`);
        err.status = resp.status;
        throw err;
    }
    return data;
};

export const User = {
    list: async () => {
        return await apiJson(`${authBase()}/users`);
    },

    update: async (userId, metadata) => {
        const updated = await apiJson(`${authBase()}/users/${encodeURIComponent(userId)}`, {
            method: 'PUT',
            body: JSON.stringify(metadata),
        });
        const session = readSession();
        if (session && session.id === userId) {
            writeSession(updated);
        }
        return updated;
    },

    signIn: async ({ email, password }) => {
        const data = await apiJson(`${authBase()}/login`, {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        setAccessToken(data.access_token);
        writeSession(data.user);
        return data.user;
    },

    devQuickSignIn: async (email) => {
        const data = await apiJson(`${authBase()}/dev-login`, {
            method: 'POST',
            body: JSON.stringify({ email }),
        });
        setAccessToken(data.access_token);
        writeSession(data.user);
        return data.user;
    },

    getDevAccounts: async () => {
        try {
            const resp = await fetch(`${authBase()}/dev-accounts`, { credentials: 'include' });
            if (!resp.ok) return { auth_mode: 'production', accounts: [] };
            return await resp.json();
        } catch {
            return { auth_mode: 'production', accounts: [] };
        }
    },

    signUp: async ({ email, password, options }) => {
        const data = await apiJson(`${authBase()}/register`, {
            method: 'POST',
            body: JSON.stringify({
                email,
                password,
                full_name: options?.data?.full_name || '',
            }),
        });
        if (data.access_token) {
            setAccessToken(data.access_token);
            writeSession(data.user);
        } else {
            clearAccessToken();
        }
        return data;
    },

    signOut: async () => {
        try {
            const token = getAccessToken();
            const headers = token ? { Authorization: `Bearer ${token}` } : {};
            await fetch(`${authBase()}/logout`, { method: 'POST', headers, credentials: 'include' });
        } catch { }
        clearAccessToken();
        writeSession(null);
        window.location.href = '/login';
    },

    getSession: async () => {
        const token = getAccessToken();
        const user = await User.me();
        if (!user) return null;
        return { access_token: token, user };
    },

    getUser: async () => {
        return await User.me();
    },

    me: async () => {
        const token = getAccessToken();
        try {
            const liveUser = await apiJson(`${authBase()}/me`);
            writeSession(liveUser);
            return liveUser;
        } catch (err) {
            if (!token || err?.status === 401 || err?.status === 403) {
                clearAccessToken();
                return null;
            }
            return readSession();
        }
    },

    updateUser: async (data) => {
        const session = readSession();
        if (!session) return null;
        return User.update(session.id, data);
    },

    resetPassword: async () => { },

    onAuthStateChange: (callback) => {
        User.me().then((sessionUser) => {
            if (sessionUser) {
                callback('SIGNED_IN', { user: sessionUser });
            } else {
                callback('SIGNED_OUT', null);
            }
        });
        return { data: { subscription: { unsubscribe: () => { } } } };
    },
};

export const auth = User;
