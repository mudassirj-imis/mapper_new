import axios from 'axios';
import { API_BASE_URL } from '../config/api';

/**
 * Shared axios instance.
 * - Base URL comes from src/config/api.js and is served through the Vite
 *   dev proxy (see vite.config.js -> server.proxy).
 * - Request interceptor injects the Bearer token stored at login.
 * - Response interceptor handles expired sessions (401) by clearing the
 *   token and bouncing the user back to /login.
 */
const api = axios.create({
  baseURL: API_BASE_URL,
  // Backend upstream calls may legitimately take up to API_TIMEOUT_SECONDS (60s)
  // plus gateway overhead, so the client must allow more than that or slow
  // upstreams surface as a client-side "timeout of 30000ms exceeded" instead of
  // the backend's real status/error.
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const TOKEN_KEY = 'token';
export const EMAIL_KEY = 'user_email';

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;

    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(EMAIL_KEY);

      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

export default api;
