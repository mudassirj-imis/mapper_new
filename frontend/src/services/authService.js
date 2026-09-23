import api from './api';

/**
 * Authentication service — talks to the backend auth API.
 *
 * Backend contract (expected):
 *   POST /api/auth/login    { email, password } -> { success, token, email? }
 *   POST /api/auth/validate (Bearer token)      -> { success, email? }
 *   POST /api/auth/logout   (Bearer token)      -> { success }
 */

export const login = async (email, password) => {
  const response = await api.post('/auth/login', { email, password });
  return response.data;
};

export const validateToken = async () => {
  const response = await api.post('/auth/validate');
  return response.data;
};

export const logout = async () => {
  const response = await api.post('/auth/logout');
  return response.data;
};

export default { login, validateToken, logout };
