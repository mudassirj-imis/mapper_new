import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Box,
  Button,
  IconButton,
  InputAdornment,
  Paper,
  TextField,
  Typography,
} from '@mui/material';
import {
  LockOutlined,
  Visibility,
  VisibilityOff,
  KeyRounded,
  LogoutRounded,
} from '@mui/icons-material';
import { alpha, useTheme } from '@mui/material/styles';
import { useAuth } from '../../context/AuthContext';

/**
 * Simple password-protection overlay.
 *
 * Two modes:
 *  1. <PasswordLock password="1234">      -> client-side gate, unlock is kept
 *     for the browser session (sessionStorage, keyed by `storageKey`).
 *  2. <PasswordLock>                      -> requires an authenticated
 *     session; visitors are pointed to /login.
 */
export default function PasswordLock({
  children,
  password,
  title = 'Restricted area',
  description = 'Enter the access password to continue.',
  storageKey = 'password-lock',
}) {
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated } = useAuth();

  const sessionKey = `passwordLock:${storageKey}`;
  const [unlocked, setUnlocked] = useState(
    () => sessionStorage.getItem(sessionKey) === 'true'
  );
  const [value, setValue] = useState('');
  const [showValue, setShowValue] = useState(false);
  const [error, setError] = useState('');
  const [shakeKey, setShakeKey] = useState(0);

  const requiresSession = !password;
  const isOpen = requiresSession ? !isAuthenticated : !unlocked;

  if (!isOpen) {
    return children;
  }

  const handleSubmit = (event) => {
    event.preventDefault();

    if (requiresSession) {
      navigate('/login', { state: { from: location.pathname } });
      return;
    }

    if (value === password) {
      sessionStorage.setItem(sessionKey, 'true');
      setUnlocked(true);
      setError('');
      return;
    }

    setError('Incorrect password. Try again.');
    setShakeKey((key) => key + 1);
    setValue('');
  };

  const primary = theme.palette.primary.main;
  const secondary = theme.palette.secondary.main;

  return (
    <Box
      sx={{
        position: 'relative',
        minHeight: 280,
      }}
    >
      {/* Blurred preview of the protected content */}
      <Box
        sx={{ filter: 'blur(7px)', opacity: 0.45, pointerEvents: 'none', userSelect: 'none' }}
        aria-hidden
      >
        {children}
      </Box>

      {/* Overlay */}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          p: 2,
          backgroundColor: alpha(theme.palette.background.default, 0.55),
          backdropFilter: 'blur(2px)',
          borderRadius: 3,
        }}
      >
        <motion.div
          key={shakeKey}
          initial={{ opacity: 0, y: 12, scale: 0.98 }}
          animate={
            shakeKey > 0
              ? { opacity: 1, y: 0, scale: 1, x: [0, -9, 9, -6, 6, 0] }
              : { opacity: 1, y: 0, scale: 1 }
          }
          transition={{ duration: shakeKey > 0 ? 0.45 : 0.3, ease: 'easeOut' }}
        >
          <Paper
            elevation={0}
            sx={{
              width: '100%',
              maxWidth: 380,
              p: 4,
              borderRadius: 3,
              border: '1px solid',
              borderColor: 'divider',
              boxShadow:
                theme.palette.mode === 'dark'
                  ? '0 24px 64px rgba(0, 0, 0, 0.55)'
                  : '0 24px 64px rgba(16, 31, 51, 0.16)',
              textAlign: 'center',
            }}
          >
            <Box
              sx={{
                width: 54,
                height: 54,
                mx: 'auto',
                mb: 2.5,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 2.5,
                background: `linear-gradient(135deg, ${primary} 0%, ${secondary} 100%)`,
                boxShadow: `0 12px 28px ${alpha(primary, 0.35)}`,
              }}
            >
              <LockOutlined sx={{ color: '#fff', fontSize: 28 }} />
            </Box>

            <Typography variant="h6" sx={{ mb: 0.75 }}>
              {title}
            </Typography>
            <Typography
              variant="body2"
              sx={{ color: 'text.secondary', mb: 3, px: 1 }}
            >
              {requiresSession ? 'Sign in to view this section.' : description}
            </Typography>

            <form onSubmit={handleSubmit}>
              {requiresSession ? (
                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  size="large"
                  startIcon={<LogoutRounded sx={{ transform: 'rotate(180deg)' }} />}
                >
                  Go to sign in
                </Button>
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <TextField
                    fullWidth
                    autoFocus
                    type={showValue ? 'text' : 'password'}
                    label="Access password"
                    value={value}
                    onChange={(event) => {
                      setValue(event.target.value);
                      if (error) setError('');
                    }}
                    error={Boolean(error)}
                    helperText={error || ' '}
                    slotProps={{
                      input: {
                        startAdornment: (
                          <InputAdornment position="start">
                            <KeyRounded sx={{ fontSize: 18, color: 'text.disabled' }} />
                          </InputAdornment>
                        ),
                        endAdornment: (
                          <InputAdornment position="end">
                            <IconButton
                              size="small"
                              edge="end"
                              onClick={() => setShowValue((prev) => !prev)}
                              aria-label={showValue ? 'Hide password' : 'Show password'}
                            >
                              {showValue ? (
                                <VisibilityOff fontSize="small" />
                              ) : (
                                <Visibility fontSize="small" />
                              )}
                            </IconButton>
                          </InputAdornment>
                        ),
                      },
                    }}
                  />
                  <Button type="submit" variant="contained" size="large">
                    Unlock
                  </Button>
                </Box>
              )}
            </form>

            <Typography
              className="mono-label"
              sx={{ display: 'block', mt: 3, color: 'text.disabled' }}
            >
              Protected section
            </Typography>
          </Paper>
        </motion.div>
      </Box>
    </Box>
  );
}
