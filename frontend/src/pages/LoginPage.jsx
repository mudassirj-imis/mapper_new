import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Alert,
  Box,
  Button,
  Card,
  CircularProgress,
  Collapse,
  IconButton,
  InputAdornment,
  TextField,
  Typography,
} from '@mui/material';
import {
  Api as ApiIcon,
  ArrowForward,
  EmailOutlined,
  LockOutlined,
  Visibility,
  VisibilityOff,
} from '@mui/icons-material';
import { alpha, useTheme } from '@mui/material/styles';
import { useAuth } from '../context/AuthContext';

const containerVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.08, delayChildren: 0.06 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 14 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] },
  },
};

function GlowOrb({ sx }) {
  return (
    <Box
      aria-hidden
      sx={{
        position: 'absolute',
        borderRadius: '50%',
        filter: 'blur(70px)',
        pointerEvents: 'none',
        animation: 'orbDrift 16s ease-in-out infinite',
        ...sx,
      }}
    />
  );
}

function AuthLoading() {
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

export default function LoginPage() {
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated, loading: authLoading } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isDark = theme.palette.mode === 'dark';
  const from =
    location.state?.from && location.state.from !== '/login' ? location.state.from : '/';

  if (authLoading) {
    return <AuthLoading />;
  }

  if (isAuthenticated) {
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError('Email or username is required.');
      return;
    }
    if (!password) {
      setError('Password is required.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      await login(trimmedEmail, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err?.message || 'Unable to sign in. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box
      sx={{
        position: 'relative',
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        px: 2,
        py: 5,
        background: isDark
          ? 'radial-gradient(1100px 700px at 12% -12%, #12233f 0%, #080f1e 58%)'
          : 'radial-gradient(1100px 700px at 12% -12%, #e6effc 0%, #f4f7fb 58%)',
      }}
    >
      {/* Blueprint grid texture */}
      <Box
        aria-hidden
        className="blueprint-grid"
        sx={{
          position: 'absolute',
          inset: 0,
          opacity: isDark ? 0.6 : 1,
          maskImage: 'radial-gradient(ellipse at center, black 0%, transparent 78%)',
          WebkitMaskImage: 'radial-gradient(ellipse at center, black 0%, transparent 78%)',
        }}
      />

      {/* Ambient glows */}
      <GlowOrb
        sx={{
          width: 420,
          height: 420,
          top: -120,
          left: -110,
          backgroundColor: alpha('#1976d2', isDark ? 0.4 : 0.22),
        }}
      />
      <GlowOrb
        sx={{
          width: 360,
          height: 360,
          bottom: -140,
          right: -90,
          backgroundColor: alpha('#9c27b0', isDark ? 0.32 : 0.16),
          animationDelay: '5s',
        }}
      />

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        style={{ position: 'relative', width: '100%', maxWidth: 430 }}
      >
        <Card
          elevation={0}
          sx={{
            p: { xs: 3, sm: 4.5 },
            borderRadius: 4,
            border: '1px solid',
            borderColor: 'divider',
            backgroundColor: alpha(theme.palette.background.paper, 0.9),
            backdropFilter: 'blur(14px)',
            boxShadow: isDark
              ? '0 32px 80px rgba(0, 0, 0, 0.5)'
              : '0 32px 80px rgba(16, 31, 51, 0.14)',
          }}
        >
          <motion.div variants={itemVariants}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3.5 }}>
              <Box
                sx={{
                  width: 44,
                  height: 44,
                  borderRadius: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'linear-gradient(135deg, #1976d2 0%, #9c27b0 100%)',
                  boxShadow: `0 10px 24px ${alpha('#1976d2', 0.35)}`,
                }}
              >
                <ApiIcon sx={{ fontSize: 24, color: '#ffffff' }} />
              </Box>
              <Box>
                <Typography sx={{ fontWeight: 700, fontSize: '1rem', lineHeight: 1.25 }}>
                  API Mapper
                </Typography>
                <Typography
                  className="mono-label"
                  sx={{ color: 'text.secondary', fontSize: '0.55rem' }}
                >
                  Integration Console
                </Typography>
              </Box>
            </Box>
          </motion.div>

          <motion.div variants={itemVariants}>
            <Typography variant="h5" sx={{ mb: 0.5 }}>
              Sign in
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
              {location.state?.from
                ? 'Sign in to continue to the console.'
                : 'Access the mapping and gateway console.'}
            </Typography>
          </motion.div>

          <motion.div variants={itemVariants}>
            <Box component="form" onSubmit={handleSubmit} noValidate>
              <TextField
                fullWidth
                autoFocus
                type="text"
                label="Email or username"
                autoComplete="username"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                  if (error) setError('');
                }}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <EmailOutlined sx={{ fontSize: 19, color: 'text.disabled' }} />
                      </InputAdornment>
                    ),
                  },
                }}
                sx={{ mb: 2 }}
              />

              <TextField
                fullWidth
                type={showPassword ? 'text' : 'password'}
                label="Password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  if (error) setError('');
                }}
                slotProps={{
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">
                        <LockOutlined sx={{ fontSize: 19, color: 'text.disabled' }} />
                      </InputAdornment>
                    ),
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          size="small"
                          edge="end"
                          onClick={() => setShowPassword((prev) => !prev)}
                          aria-label={showPassword ? 'Hide password' : 'Show password'}
                        >
                          {showPassword ? (
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

              <Collapse in={Boolean(error)}>
                <Alert severity="error" sx={{ mt: 2 }}>
                  {error}
                </Alert>
              </Collapse>

              <Button
                type="submit"
                fullWidth
                variant="contained"
                size="large"
                disabled={submitting}
                endIcon={submitting ? null : <ArrowForward fontSize="small" />}
                sx={{ mt: 3, py: 1.3 }}
              >
                {submitting ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                    <CircularProgress size={18} thickness={5} color="inherit" />
                    Signing in…
                  </Box>
                ) : (
                  'Sign in'
                )}
              </Button>
            </Box>
          </motion.div>
        </Card>

        <motion.div variants={itemVariants}>
          <Typography
            className="mono-label"
            sx={{ textAlign: 'center', mt: 3, color: 'text.disabled', fontSize: '0.55rem' }}
          >
            Secure access · API Mapper v1.0.0
          </Typography>
        </motion.div>
      </motion.div>
    </Box>
  );
}
