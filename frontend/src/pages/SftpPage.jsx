import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  IconButton,
  InputAdornment,
  MenuItem,
  Paper,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  ArrowUpwardRounded,
  DnsRounded,
  ExpandMoreRounded,
  FolderOpenRounded,
  LinkRounded,
  RefreshRounded,
  Visibility,
  VisibilityOff,
} from '@mui/icons-material';
import { alpha, lighten, useTheme } from '@mui/material/styles';

import SftpBrowser from '../components/sftp/SftpBrowser';
import FilePreview from '../components/sftp/FilePreview';
import { useApiQuery } from '../hooks/useApi';
import { getEndpoints } from '../services/endpointService';
import { listFiles, previewFile, testConnection } from '../services/sftpService';
import { useSnackbar } from '../context/SnackbarContext';

const DEFAULT_PORT = 22;

const STATUS_META = {
  disconnected: { label: 'Disconnected', color: '#546e7a' },
  testing: { label: 'Testing connection', color: '#e8a200' },
  connected: { label: 'Connected', color: '#2e7d32' },
  error: { label: 'Connection failed', color: '#d32f2f' },
};

const extractError = (error) => {
  const detail = error?.response?.data?.detail ?? error?.response?.data?.message;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((item) => item?.msg || String(item)).join('; ');
  return error?.message || 'SFTP operation failed';
};

const parentPath = (path) => {
  const clean = String(path || '/').replace(/[\\/]+$/, '');
  if (!clean) return '/';
  const index = clean.lastIndexOf('/');
  if (index <= 0) return '/';
  return clean.slice(0, index) || '/';
};

/** Connection state pill with a live indicator. */
function ConnectionStatus({ status, message }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const meta = STATUS_META[status] || STATUS_META.disconnected;
  const color = isDark ? lighten(meta.color, 0.32) : meta.color;

  return (
    <Box
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 1.25,
        px: 1.5,
        py: 0.7,
        borderRadius: 2,
        border: `1px solid ${alpha(meta.color, isDark ? 0.4 : 0.28)}`,
        backgroundColor: alpha(meta.color, isDark ? 0.14 : 0.07),
        maxWidth: '100%',
      }}
    >
      <Box sx={{ position: 'relative', width: 9, height: 9, flexShrink: 0, color }}>
        <Box sx={{ position: 'absolute', inset: 0, borderRadius: '50%', backgroundColor: 'currentColor' }} />
        {status === 'connected' && (
          <Box
            aria-hidden
            sx={{
              position: 'absolute',
              inset: 0,
              borderRadius: '50%',
              border: '1.5px solid currentColor',
              animation: 'pingRing 2s cubic-bezier(0, 0, 0.2, 1) infinite',
            }}
          />
        )}
      </Box>

      <Typography className="mono-label" sx={{ fontSize: '0.55rem', color, whiteSpace: 'nowrap' }}>
        {meta.label}
      </Typography>

      {message && (
        <Typography
          variant="caption"
          noWrap
          sx={{ color: 'text.secondary', maxWidth: { xs: 160, sm: 340 } }}
        >
          {message}
        </Typography>
      )}
    </Box>
  );
}

/**
 * SFTP browser — connect (manually or via a stored endpoint), walk the
 * remote tree and preview text-like documents before importing them.
 */
export default function SftpPage() {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const { showSnackbar } = useSnackbar();

  /* Connection form */
  const [formOpen, setFormOpen] = useState(true);
  const [source, setSource] = useState('manual');
  const [endpointId, setEndpointId] = useState('');
  const [host, setHost] = useState('');
  const [port, setPort] = useState(DEFAULT_PORT);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [preferredPath, setPreferredPath] = useState('');

  /* Connection lifecycle */
  const [status, setStatus] = useState('disconnected');
  const [statusMessage, setStatusMessage] = useState('');
  const [session, setSession] = useState(null);
  const [remotePath, setRemotePath] = useState('/');

  /* Preview dialog */
  const [preview, setPreview] = useState({
    open: false,
    loading: false,
    error: '',
    fileName: '',
    fileType: '',
    data: null,
  });

  const endpointsQuery = useApiQuery(['endpoints', 'sftp'], getEndpoints, { staleTime: 60_000 });

  const sftpEndpoints = useMemo(() => {
    const payload = endpointsQuery.data;
    const list = Array.isArray(payload) ? payload : payload?.items ?? payload?.endpoints ?? [];
    return list.filter((item) => item?.sftp_host);
  }, [endpointsQuery.data]);

  const filesQuery = useApiQuery(
    ['sftp-files', session?.id, remotePath],
    () => listFiles({ ...session.config, remote_path: remotePath }),
    { enabled: Boolean(session), retry: false, refetchOnWindowFocus: false }
  );

  const selectedEndpoint = useMemo(
    () => sftpEndpoints.find((item) => String(item.id) === String(endpointId)) || null,
    [sftpEndpoints, endpointId]
  );

  const handleEndpointSelect = (id) => {
    setEndpointId(id);
    const endpoint = sftpEndpoints.find((item) => String(item.id) === String(id));
    if (endpoint) {
      setHost(endpoint.sftp_host || '');
      setPort(endpoint.sftp_port || DEFAULT_PORT);
      setUsername(endpoint.sftp_username || '');
      setPassword('');
      setPreferredPath(endpoint.sftp_remote_path || '');
    }
  };

  const buildConfig = () => {
    const base = {
      host: host.trim() || undefined,
      port: Number(port) || DEFAULT_PORT,
      username: username.trim() || undefined,
      password: password || undefined,
    };
    if (source === 'endpoint') return { ...base, endpoint_id: endpointId || undefined };
    return base;
  };

  const handleConnect = async (event) => {
    event?.preventDefault();

    if (source === 'endpoint' && !endpointId) {
      setStatus('error');
      setStatusMessage('Select an SFTP endpoint first.');
      return;
    }
    if (source === 'manual' && !host.trim()) {
      setStatus('error');
      setStatusMessage('Host is required.');
      return;
    }

    setStatus('testing');
    setStatusMessage('');

    try {
      const config = buildConfig();
      const result = await testConnection(config);

      if (result?.success === false) {
        throw new Error(result?.message || result?.detail || 'The server refused the connection.');
      }

      const initialPath = result?.initial_path || result?.path || preferredPath || '/';
      setSession({ id: Date.now(), config });
      setRemotePath(initialPath);
      setStatus('connected');
      setStatusMessage(result?.message || `Connected to ${host.trim() || 'stored endpoint'}`);
      setFormOpen(false);
      showSnackbar(`SFTP connection established · ${host.trim() || 'endpoint credentials'}`, 'success');
    } catch (error) {
      const message = extractError(error);
      setSession(null);
      setStatus('error');
      setStatusMessage(message);
      showSnackbar(message, 'error');
    }
  };

  const handleDisconnect = () => {
    setSession(null);
    setStatus('disconnected');
    setStatusMessage('');
    setRemotePath('/');
    setFormOpen(true);
    showSnackbar('SFTP session closed', 'info');
  };

  const handlePreview = async (file) => {
    if (!session) return;

    setPreview({
      open: true,
      loading: true,
      error: '',
      fileName: file.name,
      fileType: '',
      data: null,
    });

    try {
      const result = await previewFile({
        ...session.config,
        remote_path: remotePath,
        filename: file.name,
      });
      setPreview({
        open: true,
        loading: false,
        error: '',
        fileName: result?.filename || file.name,
        fileType: result?.file_type || result?.fileType || '',
        data: result,
      });
    } catch (error) {
      setPreview((prev) => ({ ...prev, loading: false, error: extractError(error) }));
    }
  };

  const closePreview = () => setPreview((prev) => ({ ...prev, open: false }));

  const handleRefresh = () => {
    filesQuery.refetch();
  };

  const grid = { display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(12, 1fr)' }, gap: 2 };

  return (
    <Box
      component={motion.div}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}
    >
      {/* Page header */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>
        <Box sx={{ flex: 1, minWidth: 240 }}>
          <Typography className="mono-label" sx={{ color: 'text.disabled', mb: 0.5 }}>
            Storage
          </Typography>
          <Typography variant="h5" sx={{ mb: 0.5 }}>
            SFTP Browser
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Connect to a remote server, walk its folders and preview source documents before mapping.
          </Typography>
        </Box>

        <ConnectionStatus status={status} message={statusMessage} />
      </Box>

      {/* Connection card */}
      <Paper
        elevation={0}
        sx={{
          position: 'relative',
          overflow: 'hidden',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 3,
        }}
      >
        <Box
          aria-hidden
          sx={{
            position: 'absolute',
            width: 320,
            height: 320,
            top: -200,
            right: -120,
            borderRadius: '50%',
            filter: 'blur(70px)',
            pointerEvents: 'none',
            backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.07),
          }}
        />

        {/* Collapsible header */}
        <Box
          onClick={() => setFormOpen((prev) => !prev)}
          sx={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            px: { xs: 2, sm: 2.5 },
            py: 1.75,
            cursor: 'pointer',
            '&:hover': { backgroundColor: alpha(theme.palette.primary.main, 0.03) },
            transition: 'background-color 0.2s ease',
          }}
        >
          <Box
            sx={{
              width: 40,
              height: 40,
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 2,
              color: 'primary.main',
              backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
              border: `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
              '& svg': { fontSize: 20 },
            }}
          >
            <DnsRounded />
          </Box>

          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography sx={{ fontWeight: 600, fontSize: '0.92rem', lineHeight: 1.3 }}>
              Connection
            </Typography>
            <Typography className="mono-label" sx={{ color: 'text.disabled', fontSize: '0.5rem' }}>
              {session
                ? `${host || 'stored endpoint'} · port ${port}`
                : source === 'endpoint'
                  ? 'Stored endpoint credentials'
                  : 'Manual credentials'}
            </Typography>
          </Box>

          {status === 'connected' && (
            <Chip
              label={remotePath}
              size="small"
              sx={{
                display: { xs: 'none', md: 'inline-flex' },
                maxWidth: 220,
                fontFamily: theme.typography.fontFamilyCode,
                fontSize: '0.66rem',
                backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
                border: `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
              }}
            />
          )}

          <IconButton
            size="small"
            aria-label={formOpen ? 'Collapse connection form' : 'Expand connection form'}
            sx={{
              color: 'text.secondary',
              transform: formOpen ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.25s ease',
            }}
          >
            <ExpandMoreRounded fontSize="small" />
          </IconButton>
        </Box>

        <Collapse in={formOpen} timeout={260}>
          <Divider />
          <Box
            component="form"
            onSubmit={handleConnect}
            sx={{ position: 'relative', px: { xs: 2, sm: 2.5 }, py: 2.5 }}
          >
            <ToggleButtonGroup
              exclusive
              size="small"
              value={source}
              onChange={(_event, next) => {
                if (!next) return;
                setSource(next);
                if (next === 'manual') setEndpointId('');
              }}
              sx={{ mb: 2.5, '& .MuiToggleButton-root': { gap: 1, px: 2, textTransform: 'none' } }}
            >
              <ToggleButton value="manual">
                <DnsRounded sx={{ fontSize: 16 }} />
                Manual
              </ToggleButton>
              <ToggleButton value="endpoint">
                <LinkRounded sx={{ fontSize: 16 }} />
                From endpoint
              </ToggleButton>
            </ToggleButtonGroup>

            {source === 'endpoint' && (
              <TextField
                select
                fullWidth
                size="small"
                label="SFTP endpoint"
                value={endpointId}
                onChange={(event) => handleEndpointSelect(event.target.value)}
                disabled={endpointsQuery.isLoading}
                helperText={
                  sftpEndpoints.length === 0 && !endpointsQuery.isLoading
                    ? 'No endpoints have SFTP configured yet — switch to manual mode.'
                    : 'Stored credentials are decrypted server-side; leave the password empty to use them.'
                }
                sx={{ mb: 2.5 }}
              >
                {sftpEndpoints.map((endpoint) => (
                  <MenuItem key={endpoint.id} value={endpoint.id}>
                    {`${endpoint.endpoint_code || endpoint.name || endpoint.id} — ${endpoint.sftp_host}:${endpoint.sftp_port || DEFAULT_PORT}`}
                  </MenuItem>
                ))}
              </TextField>
            )}

            <Box sx={grid}>
              <Box sx={{ gridColumn: { xs: 'auto', sm: 'span 8' } }}>
                <TextField
                  fullWidth
                  size="small"
                  label="Host"
                  placeholder="sftp.example.com"
                  value={host}
                  onChange={(event) => setHost(event.target.value)}
                  autoComplete="off"
                />
              </Box>

              <Box sx={{ gridColumn: { xs: 'auto', sm: 'span 4' } }}>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="Port"
                  value={port}
                  onChange={(event) => setPort(event.target.value)}
                  slotProps={{ htmlInput: { min: 1, max: 65535 } }}
                />
              </Box>

              <Box sx={{ gridColumn: { xs: 'auto', sm: 'span 6' } }}>
                <TextField
                  fullWidth
                  size="small"
                  label="Username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="off"
                />
              </Box>

              <Box sx={{ gridColumn: { xs: 'auto', sm: 'span 6' } }}>
                <TextField
                  fullWidth
                  size="small"
                  type={showPassword ? 'text' : 'password'}
                  label="Password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  slotProps={{
                    input: {
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton
                            size="small"
                            edge="end"
                            onClick={() => setShowPassword((prev) => !prev)}
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                          >
                            {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                          </IconButton>
                        </InputAdornment>
                      ),
                    },
                  }}
                />
              </Box>
            </Box>

            {selectedEndpoint?.description && (
              <Typography variant="caption" sx={{ display: 'block', mt: 1.5, color: 'text.secondary' }}>
                {selectedEndpoint.description}
              </Typography>
            )}

            <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, mt: 3 }}>
              <Button
                type="submit"
                variant="contained"
                startIcon={
                  status === 'testing' ? <CircularProgress size={16} thickness={5} color="inherit" /> : <DnsRounded />
                }
                disabled={status === 'testing'}
              >
                {status === 'testing' ? 'Testing connection…' : 'Test connection'}
              </Button>

              {session && (
                <>
                  <Button variant="text" color="inherit" onClick={handleDisconnect} sx={{ color: 'text.secondary' }}>
                    Disconnect
                  </Button>
                  <Typography variant="caption" sx={{ color: 'text.disabled' }}>
                    Testing again replaces the active session.
                  </Typography>
                </>
              )}
            </Box>
          </Box>
        </Collapse>
      </Paper>

      {/* Browser card */}
      {session ? (
        <Paper
          elevation={0}
          sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 3, p: { xs: 1.5, sm: 2.5 } }}
        >
          <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, mb: 2 }}>
            <Tooltip title="Up one level" arrow>
              <span>
                <IconButton size="small" onClick={() => setRemotePath((prev) => parentPath(prev))} disabled={remotePath === '/'} aria-label="Go up one level">
                  <ArrowUpwardRounded fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>

            <Tooltip title="Refresh listing" arrow>
              <span>
                <IconButton size="small" onClick={handleRefresh} disabled={filesQuery.isFetching} aria-label="Refresh listing">
                  {filesQuery.isFetching ? (
                    <CircularProgress size={15} thickness={5} />
                  ) : (
                    <RefreshRounded fontSize="small" />
                  )}
                </IconButton>
              </span>
            </Tooltip>

            <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

            <Typography
              sx={{
                fontFamily: theme.typography.fontFamilyCode,
                fontSize: '0.76rem',
                color: 'text.secondary',
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {remotePath}
            </Typography>

            <Box sx={{ flex: 1 }} />

            <Typography className="mono-label" sx={{ color: 'text.disabled', fontSize: '0.5rem', display: { xs: 'none', sm: 'block' } }}>
              Double-click a row to open
            </Typography>
          </Box>

          {filesQuery.isError && (
            <Alert
              severity="error"
              sx={{ mb: 2 }}
              action={
                <Button color="inherit" size="small" onClick={handleRefresh}>
                  Retry
                </Button>
              }
            >
              {extractError(filesQuery.error)}
            </Alert>
          )}

          <SftpBrowser
            files={filesQuery.data}
            currentPath={remotePath}
            onNavigate={setRemotePath}
            onPreview={handlePreview}
            loading={Boolean(session) && filesQuery.isPending && !filesQuery.isError}
          />
        </Paper>
      ) : (
        <Paper
          elevation={0}
          sx={{
            position: 'relative',
            overflow: 'hidden',
            border: '1px dashed',
            borderColor: 'divider',
            borderRadius: 3,
            py: { xs: 6, sm: 8 },
            px: 3,
            textAlign: 'center',
          }}
        >
          <Box
            sx={{
              width: 58,
              height: 58,
              mx: 'auto',
              mb: 2.5,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 2.5,
              border: `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
              backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08),
              color: 'primary.main',
              '& svg': { fontSize: 28 },
            }}
          >
            <FolderOpenRounded />
          </Box>
          <Typography variant="h6" sx={{ mb: 0.75 }}>
            No active connection
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', maxWidth: 460, mx: 'auto' }}>
            Fill in the connection form above — or pick a stored SFTP endpoint — and run a connection test to
            start browsing the remote directory tree.
          </Typography>
          <Typography className="mono-label" sx={{ mt: 3, color: 'text.disabled', fontSize: '0.5rem' }}>
            Step 1 · connect · Step 2 · browse · Step 3 · preview
          </Typography>
        </Paper>
      )}

      {/* File preview dialog */}
      <FilePreview
        open={preview.open}
        onClose={closePreview}
        fileData={preview.data}
        fileName={preview.fileName}
        fileType={preview.fileType}
        loading={preview.loading}
        error={preview.error}
      />
    </Box>
  );
}
