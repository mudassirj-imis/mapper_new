import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Box, CircularProgress, Typography } from '@mui/material';
import authService from '../services/authService';
import { TOKEN_KEY, EMAIL_KEY } from '../services/api';

const AuthContext = createContext(null);

/**
 * Full-screen loader shown while an existing session token is validated.
 */
function SessionLoader() {
  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        bgcolor: 'background.default',
      }}
    >
      <CircularProgress size={30} thickness={4.5} />
      <Typography className="mono-label" sx={{ color: 'text.secondary' }}>
        Authenticating
      </Typography>
    </Box>
  );
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(() => localStorage.getItem(EMAIL_KEY));
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  const applySession = useCallback((nextToken, nextEmail) => {
    if (nextToken) localStorage.setItem(TOKEN_KEY, nextToken);
    if (nextEmail) localStorage.setItem(EMAIL_KEY, nextEmail);
    setToken(nextToken || null);
    setUser(nextEmail || null);
    setIsAuthenticated(Boolean(nextToken));
  }, []);

  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
    setToken(null);
    setUser(null);
    setIsAuthenticated(false);
  }, []);

  /**
   * Validate the token currently stored in localStorage.
   * Returns true when the session is (still) valid.
   */
  const validateToken = useCallback(async () => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setIsAuthenticated(false);
      return false;
    }

    try {
      const data = await authService.validateToken();
      if (data?.success) {
        const email = data.email || data.user?.email || localStorage.getItem(EMAIL_KEY);
        applySession(stored, email);
        return true;
      }
      clearSession();
      return false;
    } catch {
      clearSession();
      return false;
    }
  }, [applySession, clearSession]);

  // On mount: try to validate any existing token.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      await validateToken();
      if (!cancelled) setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [validateToken]);

  const login = useCallback(
    async (email, password) => {
      const data = await authService.login(email, password);
      if (!data?.success || !data.token) {
        throw new Error(data?.detail || data?.message || 'Invalid email or password');
      }
      applySession(data.token, data.email || data.user?.email || email);
      return data;
    },
    [applySession]
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      // Logout should never block the UI — ignore network / server errors.
    }
    clearSession();
  }, [clearSession]);

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated,
      loading,
      login,
      logout,
      validateToken,
    }),
    [user, token, isAuthenticated, loading, login, logout, validateToken]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

/**
 * Route guard — redirects unauthenticated visitors to /login while the
 * initial token check is running it shows a full-screen loader.
 */
export function AuthGuard({ children }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <SessionLoader />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return children;
}

export default AuthContext;
