import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  List,
  ListItem,
  MenuItem,
  Paper,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  CheckCircleRounded,
  CloseRounded,
  CloudUploadRounded,
  DataObjectRounded,
  DeleteOutlineRounded,
  DownloadRounded,
  ErrorOutlineRounded,
  HistoryRounded,
  SendRounded,
  TableViewRounded,
  UploadFileRounded,
} from '@mui/icons-material';
import { alpha, lighten, useTheme } from '@mui/material/styles';

import {
  IMPORT_HANDLERS,
  downloadBlob,
  exportCsv,
  exportJson,
  exportPostman,
  readApiError,
} from '../services/exportImportService';
import { useSnackbar } from '../context/SnackbarContext';

const HISTORY_LIMIT = 8;

const timestamp = () => new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');

const EXPORT_FORMATS = [
  {
    id: 'json',
    title: 'JSON bundle',
    description: 'Complete mapping bundle — endpoints, parameter rules, delivery mode and behaviour flags.',
    spec: '.json · full fidelity',
    Icon: DataObjectRounded,
    color: '#1976d2',
    run: exportJson,
    filename: () => `api-mapper-export-${timestamp()}.json`,
  },
  {
    id: 'csv',
    title: 'CSV sheet',
    description: 'Flat spreadsheet of every field mapping — ideal for reviews and hand-offs.',
    spec: '.csv · flat rows',
    Icon: TableViewRounded,
    color: '#9c27b0',
    run: exportCsv,
    filename: () => `api-mapper-export-${timestamp()}.csv`,
  },
  {
    id: 'postman',
    title: 'Postman collection',
    description: 'Portable v2.1 collection with one request per mapped endpoint, ready to share.',
    spec: '.postman_collection.json',
    Icon: SendRounded,
    color: '#2e7d32',
    run: exportPostman,
    filename: () => `api-mapper-postman-${timestamp()}.postman_collection.json`,
  },
];

const IMPORT_FORMATS = [
  { id: 'json', label: 'JSON bundle', Icon: DataObjectRounded, color: '#1976d2' },
  { id: 'csv', label: 'CSV sheet', Icon: TableViewRounded, color: '#9c27b0' },
  { id: 'postman', label: 'Postman collection', Icon: SendRounded, color: '#2e7d32' },
];

const FORMAT_LABEL = Object.fromEntries(IMPORT_FORMATS.map((format) => [format.id, format.label]));

const detectFormat = (file) => {
  const name = String(file?.name || '').toLowerCase();
  if (name.endsWith('.postman_collection.json') || name.includes('postman')) return 'postman';
  if (name.endsWith('.json')) return 'json';
  if (name.endsWith('.csv') || name.endsWith('.tsv')) return 'csv';
  return '';
};

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${index === 0 || value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
};

const timeAgo = (date) => {
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 45) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return date.toLocaleDateString();
};

const toCount = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
};

/**
 * Export / Import — portable mapping bundles.
 * Export: JSON / CSV / Postman downloads.
 * Import: drag-and-drop with format auto-detection and in-memory history.
 */
export default function ExportImportPage() {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const { showSnackbar } = useSnackbar();
  const queryClient = useQueryClient();

  const fileInputRef = useRef(null);

  const [exporting, setExporting] = useState('');
  const [file, setFile] = useState(null);
  const [formatOverride, setFormatOverride] = useState('');
  const [fileError, setFileError] = useState('');
  const [dragging, setDragging] = useState(false);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);

  const detectedFormat = file ? detectFormat(file) : '';
  const effectiveFormat = formatOverride || detectedFormat;
  const activeFormatMeta = IMPORT_FORMATS.find((format) => format.id === effectiveFormat) || null;

  const pushHistory = (entry) =>
    setHistory((prev) => [{ id: Date.now() + Math.random(), timestamp: new Date(), ...entry }, ...prev].slice(0, HISTORY_LIMIT));

  /* ------------------------------- export ------------------------------- */

  const handleExport = async (format) => {
    setExporting(format.id);
    try {
      const blob = await format.run();
      downloadBlob(blob, format.filename());
      showSnackbar(`${format.title} export started`, 'success');
    } catch (error) {
      showSnackbar(await readApiError(error), 'error');
    } finally {
      setExporting('');
    }
  };

  /* ------------------------------- import ------------------------------- */

  const acceptFile = (nextFile) => {
    if (!nextFile) return;
    setResult(null);
    setFormatOverride('');
    setFile(nextFile);
    setFileError(
      detectFormat(nextFile)
        ? ''
        : 'Format could not be detected from the extension — pick one manually below.'
    );
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer?.files?.[0]);
  };

  const clearFile = () => {
    setFile(null);
    setFormatOverride('');
    setFileError('');
    setResult(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleImport = async () => {
    if (!file || !effectiveFormat) return;

    setImporting(true);
    setResult(null);

    try {
      const response = await IMPORT_HANDLERS[effectiveFormat](file);

      const endpointsCount = toCount(
        response?.imported_endpoints ?? response?.endpoints_imported ?? response?.endpoints ?? response?.count
      );
      const mappingsCount = toCount(response?.imported_mappings ?? response?.mappings_imported ?? response?.mappings);
      const errors = Array.isArray(response?.errors) ? response.errors.filter(Boolean) : [];

      const message = `Imported ${endpointsCount} endpoint${endpointsCount === 1 ? '' : 's'} and ${mappingsCount} mapping${mappingsCount === 1 ? '' : 's'}.`;

      setResult({ status: errors.length ? 'warning' : 'success', message, errors });
      pushHistory({
        name: file.name,
        size: file.size,
        format: effectiveFormat,
        status: errors.length ? 'warning' : 'success',
        message,
      });
      showSnackbar(message, errors.length ? 'warning' : 'success');

      // Keep endpoint lists elsewhere in the console in sync.
      queryClient.invalidateQueries({ queryKey: ['endpoints'] });

      setFile(null);
      setFormatOverride('');
      setFileError('');
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (error) {
      const message = await readApiError(error);
      setResult({ status: 'error', message, errors: [] });
      pushHistory({ name: file.name, size: file.size, format: effectiveFormat, status: 'error', message });
      showSnackbar(message, 'error');
    } finally {
      setImporting(false);
    }
  };

  /* ------------------------------- render ------------------------------- */

  const statusColor = (status) =>
    status === 'success' ? '#2e7d32' : status === 'warning' ? '#e8a200' : '#d32f2f';

  const FileIcon = activeFormatMeta?.Icon || UploadFileRounded;

  return (
    <Box
      component={motion.div}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}
    >
      {/* Page header */}
      <Box>
        <Typography className="mono-label" sx={{ color: 'text.disabled', mb: 0.5 }}>
          Data
        </Typography>
        <Typography variant="h5" sx={{ mb: 0.5 }}>
          Export / Import
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          Move mapping bundles between environments — download portable archives or drop a file to restore.
        </Typography>
      </Box>

      {/* ------------------------------ Export ------------------------------ */}
      <Box component="section">
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5, mb: 2 }}>
          <Typography variant="h6" sx={{ fontSize: '1rem' }}>
            Export
          </Typography>
          <Typography className="mono-label" sx={{ color: 'text.disabled', fontSize: '0.5rem' }}>
            Pull a snapshot
          </Typography>
        </Box>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
            gap: 2,
          }}
        >
          {EXPORT_FORMATS.map((format) => {
            const busy = exporting === format.id;
            const anyBusy = Boolean(exporting);
            const iconColor = isDark ? lighten(format.color, 0.3) : format.color;

            return (
              <Paper
                key={format.id}
                elevation={0}
                sx={{
                  position: 'relative',
                  overflow: 'hidden',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1.5,
                  p: 2.5,
                  borderRadius: 3,
                  border: '1px solid',
                  borderColor: 'divider',
                  transition: 'transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease',
                  '&:hover': {
                    transform: 'translateY(-3px)',
                    borderColor: alpha(format.color, isDark ? 0.5 : 0.35),
                    boxShadow: isDark
                      ? `0 18px 40px ${alpha('#000000', 0.45)}`
                      : `0 18px 40px ${alpha('#101f33', 0.12)}`,
                  },
                }}
              >
                <Box
                  sx={{
                    width: 44,
                    height: 44,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: 2,
                    color: iconColor,
                    backgroundColor: alpha(format.color, isDark ? 0.16 : 0.09),
                    border: `1px solid ${alpha(format.color, isDark ? 0.38 : 0.24)}`,
                    '& svg': { fontSize: 22 },
                  }}
                >
                  <format.Icon />
                </Box>

                <Box>
                  <Typography sx={{ fontWeight: 600, mb: 0.5 }}>{format.title}</Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    {format.description}
                  </Typography>
                </Box>

                <Typography
                  className="mono-label"
                  sx={{ color: 'text.disabled', fontSize: '0.5rem', mt: 'auto' }}
                >
                  {format.spec}
                </Typography>

                <Divider sx={{ borderStyle: 'dashed' }} />

                <Button
                  fullWidth
                  variant="outlined"
                  startIcon={busy ? <CircularProgress size={15} thickness={5} color="inherit" /> : <DownloadRounded />}
                  onClick={() => handleExport(format)}
                  disabled={busy || (anyBusy && !busy)}
                >
                  {busy ? 'Preparing…' : `Export ${format.id === 'postman' ? 'collection' : format.id.toUpperCase()}`}
                </Button>
              </Paper>
            );
          })}
        </Box>
      </Box>

      {/* ------------------------------ Import ------------------------------ */}
      <Box component="section">
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5, mb: 2 }}>
          <Typography variant="h6" sx={{ fontSize: '1rem' }}>
            Import
          </Typography>
          <Typography className="mono-label" sx={{ color: 'text.disabled', fontSize: '0.5rem' }}>
            Restore a bundle
          </Typography>
        </Box>

        {/* Drop zone */}
        <Box
          role="button"
          tabIndex={0}
          aria-label="Drop a mapping bundle or browse for a file"
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          sx={{
            position: 'relative',
            overflow: 'hidden',
            cursor: 'pointer',
            textAlign: 'center',
            px: 3,
            py: { xs: 5, sm: 7 },
            border: '2px dashed',
            borderColor: dragging ? 'primary.main' : alpha(theme.palette.text.primary, isDark ? 0.22 : 0.16),
            borderRadius: 3,
            backgroundColor: dragging
              ? alpha(theme.palette.primary.main, isDark ? 0.12 : 0.06)
              : alpha(theme.palette.text.primary, isDark ? 0.02 : 0.01),
            transition: 'border-color 0.2s ease, background-color 0.2s ease, transform 0.2s ease',
            transform: dragging ? 'scale(1.004)' : 'scale(1)',
            '&:hover': {
              borderColor: alpha(theme.palette.primary.main, dragging ? 1 : 0.55),
              backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.08 : 0.04),
            },
          }}
        >
          <Box
            aria-hidden
            sx={{
              position: 'absolute',
              width: 300,
              height: 300,
              top: -190,
              left: '50%',
              ml: '-150px',
              borderRadius: '50%',
              filter: 'blur(70px)',
              pointerEvents: 'none',
              opacity: dragging ? 1 : 0.6,
              transition: 'opacity 0.25s ease',
              backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.18 : 0.09),
            }}
          />

          <motion.div
            animate={{ y: dragging ? -6 : 0, scale: dragging ? 1.06 : 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 22 }}
            style={{ position: 'relative' }}
          >
            <Box
              sx={{
                width: 62,
                height: 62,
                mx: 'auto',
                mb: 2.5,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 3,
                color: 'primary.main',
                backgroundColor: alpha(theme.palette.primary.main, isDark ? 0.16 : 0.09),
                border: `1px solid ${alpha(theme.palette.primary.main, 0.3)}`,
                '& svg': { fontSize: 30 },
              }}
            >
              <CloudUploadRounded />
            </Box>

            <Typography sx={{ fontWeight: 600, mb: 0.5 }}>
              {dragging ? 'Drop to import' : 'Drag & drop a bundle here'}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2.5 }}>
              or{' '}
              <Box component="span" sx={{ color: 'primary.main', fontWeight: 600 }}>
                browse your files
              </Box>
            </Typography>

            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.75, flexWrap: 'wrap' }}>
              {['.json', '.csv', '.postman_collection.json'].map((ext) => (
                <Chip
                  key={ext}
                  label={ext}
                  size="small"
                  sx={{
                    fontFamily: theme.typography.fontFamilyCode,
                    fontSize: '0.64rem',
                    height: 22,
                    backgroundColor: alpha(theme.palette.text.primary, isDark ? 0.06 : 0.04),
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                />
              ))}
            </Box>
          </motion.div>

          <input
            ref={fileInputRef}
            type="file"
            hidden
            accept=".json,.csv,.tsv,.postman_collection.json,application/json,text/csv"
            onChange={(event) => {
              acceptFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
        </Box>

        {/* File info + controls */}
        {file && (
          <Paper
            elevation={0}
            sx={{
              mt: 2,
              p: { xs: 1.5, sm: 2 },
              borderRadius: 2.5,
              border: '1px solid',
              borderColor: 'divider',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 1.5,
            }}
          >
            <Box
              sx={{
                width: 38,
                height: 38,
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 2,
                color: activeFormatMeta ? (isDark ? lighten(activeFormatMeta.color, 0.3) : activeFormatMeta.color) : 'text.secondary',
                backgroundColor: alpha(activeFormatMeta?.color || theme.palette.text.primary, isDark ? 0.14 : 0.07),
                border: `1px solid ${alpha(activeFormatMeta?.color || theme.palette.text.primary, 0.25)}`,
                '& svg': { fontSize: 19 },
              }}
            >
              <FileIcon />
            </Box>

            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography
                noWrap
                sx={{ fontFamily: theme.typography.fontFamilyCode, fontSize: '0.8rem', fontWeight: 600 }}
              >
                {file.name}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {formatBytes(file.size)}
                {effectiveFormat ? ` · ${FORMAT_LABEL[effectiveFormat]}` : ' · unknown format'}
              </Typography>
            </Box>

            <Tooltip title="Remove file" arrow>
              <IconButton size="small" onClick={clearFile} aria-label="Remove selected file">
                <CloseRounded fontSize="small" />
              </IconButton>
            </Tooltip>

            <Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', sm: 'block' } }} />

            <TextField
              select
              size="small"
              label="Import format"
              value={formatOverride}
              onChange={(event) => setFormatOverride(event.target.value)}
              helperText={
                detectedFormat
                  ? `Detected from extension: ${FORMAT_LABEL[detectedFormat]}`
                  : 'Not detected — choose a format manually.'
              }
              sx={{ minWidth: { xs: '100%', sm: 230 } }}
            >
              <MenuItem value="">
                {`Auto-detect${detectedFormat ? ` (${FORMAT_LABEL[detectedFormat]})` : ''}`}
              </MenuItem>
              {IMPORT_FORMATS.map((format) => (
                <MenuItem key={format.id} value={format.id}>
                  {format.label}
                </MenuItem>
              ))}
            </TextField>

            <Button
              variant="contained"
              startIcon={importing ? <CircularProgress size={16} thickness={5} color="inherit" /> : <UploadFileRounded />}
              onClick={handleImport}
              disabled={importing || !effectiveFormat}
              sx={{ minWidth: 140 }}
            >
              {importing ? 'Importing…' : 'Import'}
            </Button>
          </Paper>
        )}

        {fileError && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            {fileError}
          </Alert>
        )}

        {/* Import result */}
        {result && (
          <Alert
            severity={result.status === 'warning' ? 'warning' : result.status}
            sx={{ mt: 2 }}
            onClose={() => setResult(null)}
          >
            {result.message}
            {result.errors.length > 0 && (
              <Box component="ul" sx={{ m: 0, mt: 1, pl: 2.5 }}>
                {result.errors.slice(0, 5).map((item, index) => (
                  <li key={index}>
                    <Typography variant="caption">{typeof item === 'string' ? item : item?.message || String(item)}</Typography>
                  </li>
                ))}
                {result.errors.length > 5 && (
                  <li>
                    <Typography variant="caption">…and {result.errors.length - 5} more</Typography>
                  </li>
                )}
              </Box>
            )}
          </Alert>
        )}

        {/* Import history */}
        <Paper
          elevation={0}
          sx={{ mt: 2.5, borderRadius: 3, border: '1px solid', borderColor: 'divider', overflow: 'hidden' }}
        >
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1.25,
              px: 2,
              py: 1.5,
              borderBottom: history.length ? '1px solid' : 'none',
              borderColor: 'divider',
            }}
          >
            <HistoryRounded sx={{ fontSize: 18, color: 'text.secondary' }} />
            <Typography sx={{ fontWeight: 600, fontSize: '0.85rem', flex: 1 }}>
              Recent imports
              {history.length > 0 && (
                <Typography component="span" className="mono-label" sx={{ ml: 1, color: 'text.disabled', fontSize: '0.5rem' }}>
                  session only
                </Typography>
              )}
            </Typography>

            {history.length > 0 && (
              <Tooltip title="Clear history" arrow>
                <IconButton size="small" onClick={() => setHistory([])} aria-label="Clear import history">
                  <DeleteOutlineRounded fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
          </Box>

          {history.length === 0 ? (
            <Typography variant="body2" sx={{ color: 'text.secondary', px: 2, py: 2.5 }}>
              Imports performed in this session will be listed here.
            </Typography>
          ) : (
            <List disablePadding>
              {history.map((entry) => {
                const color = statusColor(entry.status);
                const entryColor = isDark ? lighten(color, 0.3) : color;

                return (
                  <ListItem
                    key={entry.id}
                    sx={{
                      gap: 1.5,
                      px: 2,
                      py: 1.25,
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                      '&:last-of-type': { borderBottom: 0 },
                    }}
                  >
                    <Box sx={{ display: 'inline-flex', color: entryColor, flexShrink: 0 }}>
                      {entry.status === 'success' ? (
                        <CheckCircleRounded sx={{ fontSize: 19 }} />
                      ) : (
                        <ErrorOutlineRounded sx={{ fontSize: 19 }} />
                      )}
                    </Box>

                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Typography
                        noWrap
                        sx={{ fontFamily: theme.typography.fontFamilyCode, fontSize: '0.78rem', fontWeight: 600 }}
                      >
                        {entry.name}
                      </Typography>
                      <Typography
                        variant="caption"
                        noWrap
                        sx={{ display: 'block', color: 'text.secondary' }}
                      >
                        {entry.message}
                      </Typography>
                    </Box>

                    <Chip
                      label={FORMAT_LABEL[entry.format] || entry.format}
                      size="small"
                      variant="outlined"
                      sx={{ display: { xs: 'none', sm: 'inline-flex' }, fontSize: '0.64rem', height: 22 }}
                    />

                    <Typography
                      className="mono-label"
                      sx={{ color: 'text.disabled', fontSize: '0.48rem', whiteSpace: 'nowrap' }}
                    >
                      {timeAgo(entry.timestamp)}
                    </Typography>
                  </ListItem>
                );
              })}
            </List>
          )}
        </Paper>
      </Box>
    </Box>
  );
}
