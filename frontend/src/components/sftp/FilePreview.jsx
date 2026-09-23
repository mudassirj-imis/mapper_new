import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  CloseRounded,
  ContentCopyRounded,
  DataObjectRounded,
  DescriptionRounded,
  DownloadRounded,
  InsertDriveFileRounded,
  TableViewRounded,
} from '@mui/icons-material';
import { alpha, lighten, useTheme } from '@mui/material/styles';

import { downloadBlob } from '../../services/exportImportService';
import { useSnackbar } from '../../context/SnackbarContext';

/**
 * Remote file preview dialog.
 *
 * Props:
 *   open      dialog visibility
 *   onClose   close handler
 *   fileData  preview payload — a raw string, or { content, file_type, size }
 *   fileName  displayed file name
 *   fileType  explicit type hint ('csv' | 'json' | 'text' | …)
 *   loading   preview request in-flight
 *   error     preview request error message
 */

const MAX_PREVIEW_ROWS = 300;

const TEXT_EXTENSIONS = new Set([
  'txt', 'log', 'md', 'xml', 'yml', 'yaml', 'ini', 'conf', 'env', 'sql',
  'html', 'htm', 'js', 'ts', 'tsx', 'jsx', 'py', 'java', 'go', 'rs', 'sh', 'bat', 'ps1',
]);

const KIND_META = {
  csv: { label: 'CSV', Icon: TableViewRounded, color: '#2e7d32' },
  json: { label: 'JSON', Icon: DataObjectRounded, color: '#1976d2' },
  text: { label: 'Text', Icon: DescriptionRounded, color: '#9c27b0' },
  file: { label: 'File', Icon: InsertDriveFileRounded, color: '#546e7a' },
};

/* ------------------------------- helpers ------------------------------- */

const extensionOf = (name = '') => {
  const parts = String(name).split('.');
  return parts.length > 1 ? parts.pop().toLowerCase() : '';
};

const guessKind = (name) => {
  const ext = extensionOf(name);
  if (ext === 'csv' || ext === 'tsv') return 'csv';
  if (ext === 'json') return 'json';
  if (TEXT_EXTENSIONS.has(ext)) return 'text';
  return 'file';
};

const resolveContent = (data) => {
  if (data === null || data === undefined) return '';
  if (typeof data === 'string') return data;
  if (typeof data === 'object') {
    for (const key of ['content', 'text', 'body', 'data']) {
      const value = data[key];
      if (typeof value === 'string') return value;
      if (value !== null && typeof value === 'object') return JSON.stringify(value, null, 2);
    }
    return JSON.stringify(data, null, 2);
  }
  return String(data);
};

const parseDelimited = (text) => {
  const firstLine = String(text).split(/\r?\n/)[0] || '';
  const count = (char) => (firstLine.match(new RegExp(char === '\t' ? '\\t' : `\\${char}`, 'g')) || []).length;
  const commas = count(',');
  const semicolons = count(';');
  const tabs = count('\t');
  if (tabs > commas && tabs > semicolons) return '\t';
  if (semicolons > commas) return ';';
  return ',';
};

const parseCsvRows = (text, delimiter = ',') => {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === delimiter) {
      row.push(field);
      field = '';
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }

  if (field !== '' || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows.filter((cells) => cells.some((cell) => String(cell).trim() !== ''));
};

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return null;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${index === 0 || value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
};

/* ------------------------------ component ------------------------------ */

export default function FilePreview({
  open,
  onClose,
  fileData,
  fileName = '',
  fileType,
  loading = false,
  error = '',
}) {
  const theme = useTheme();
  const { showSnackbar } = useSnackbar();
  const isDark = theme.palette.mode === 'dark';

  const [showAllRows, setShowAllRows] = useState(false);

  // Adjust state during render when a different file is opened
  // (https://react.dev/reference/react/useState — "storing information from
  // previous renders") — avoids a cascading update inside an effect.
  const previewKey = `${open ? 'open' : 'closed'}:${fileName}:${fileType || ''}`;
  const [trackedKey, setTrackedKey] = useState(previewKey);
  if (previewKey !== trackedKey) {
    setTrackedKey(previewKey);
    if (showAllRows) setShowAllRows(false);
  }

  const payload = fileData && typeof fileData === 'object' ? fileData : null;

  const rawContent = useMemo(() => resolveContent(fileData), [fileData]);

  const kind = useMemo(() => {
    const declared = String(fileType || payload?.file_type || payload?.fileType || '').toLowerCase();
    if (declared.includes('csv') || declared.includes('tsv') || declared.includes('excel')) return 'csv';
    if (declared.includes('json')) return 'json';

    const guessed = guessKind(fileName);
    if (guessed !== 'file') return guessed;

    // Unknown extension but the backend sent text — preview it as text.
    const declaredText = ['text', 'txt', 'plain', 'xml', 'yaml', 'log', 'html'].some((token) =>
      declared.includes(token)
    );
    if (declaredText || rawContent) return 'text';
    return 'file';
  }, [fileType, fileName, payload, rawContent]);

  const csvRows = useMemo(() => {
    if (kind !== 'csv' || !rawContent) return [];
    return parseCsvRows(rawContent, parseDelimited(rawContent));
  }, [kind, rawContent]);

  const jsonText = useMemo(() => {
    if (kind !== 'json' || !rawContent) return '';
    try {
      return JSON.stringify(JSON.parse(rawContent), null, 2);
    } catch {
      return rawContent;
    }
  }, [kind, rawContent]);

  const meta = KIND_META[kind] || KIND_META.file;
  const iconColor = isDark ? lighten(meta.color, 0.3) : meta.color;
  const sizeLabel = formatBytes(Number(payload?.size)) ?? null;

  const statsLabel =
    kind === 'csv' && csvRows.length
      ? `${csvRows.length} rows × ${Math.max(...csvRows.map((row) => row.length))} cols`
      : rawContent
        ? `${rawContent.split(/\r?\n/).length} lines`
        : '';

  // Console-style surface adapts to the active palette.
  const panel = isDark
    ? {
        bg: '#0a1424',
        border: alpha('#93a4bd', 0.22),
        text: '#d7e3f4',
        chromeBg: alpha('#ffffff', 0.035),
        chromeText: '#8ea1bd',
      }
    : {
        bg: '#f7f9fc',
        border: theme.palette.divider,
        text: '#14243c',
        chromeBg: alpha('#101f33', 0.035),
        chromeText: theme.palette.text.secondary,
      };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(rawContent);
      showSnackbar('File content copied to clipboard', 'success');
    } catch {
      showSnackbar('Clipboard access was blocked by the browser', 'error');
    }
  };

  const handleDownload = () => {
    const mime =
      kind === 'csv' ? 'text/csv;charset=utf-8' : kind === 'json' ? 'application/json' : 'text/plain;charset=utf-8';
    downloadBlob(new Blob([rawContent], { type: mime }), fileName || 'download.txt');
  };

  const visibleRows = showAllRows ? csvRows : csvRows.slice(0, MAX_PREVIEW_ROWS);
  const hiddenRowCount = csvRows.length - visibleRows.length;

  const tableSx = {
    '& .MuiTableCell-root': {
      fontFamily: kind === 'csv' ? theme.typography.fontFamilyCode : undefined,
      fontSize: '0.74rem',
      borderColor: 'divider',
      whiteSpace: 'nowrap',
    },
  };

  return (
    <Dialog
      open={open}
      onClose={loading ? undefined : onClose}
      fullWidth
      maxWidth="lg"
      slotProps={{ paper: { sx: { maxHeight: '88vh', display: 'flex', flexDirection: 'column' } } }}
    >
      <DialogTitle sx={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 1.5, pr: 6 }}>
        <Box
          sx={{
            width: 38,
            height: 38,
            borderRadius: 2,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: iconColor,
            backgroundColor: alpha(meta.color, isDark ? 0.16 : 0.09),
            border: `1px solid ${alpha(meta.color, isDark ? 0.38 : 0.24)}`,
            '& svg': { fontSize: 20 },
          }}
        >
          <meta.Icon />
        </Box>

        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            noWrap
            sx={{ fontFamily: theme.typography.fontFamilyCode, fontWeight: 600, fontSize: '0.88rem' }}
          >
            {fileName || payload?.filename || 'File preview'}
          </Typography>
          <Typography className="mono-label" sx={{ color: 'text.disabled', fontSize: '0.5rem' }}>
            {meta.label} preview{statsLabel ? ` · ${statsLabel}` : ''}
          </Typography>
        </Box>

        {sizeLabel && <Chip label={sizeLabel} size="small" variant="outlined" sx={{ fontSize: '0.66rem' }} />}

        <IconButton onClick={onClose} sx={{ position: 'absolute', right: 12, top: 12 }} aria-label="Close preview">
          <CloseRounded fontSize="small" />
        </IconButton>
      </DialogTitle>

      <Divider />

      <DialogContent sx={{ p: { xs: 1.5, sm: 2.5 }, overflowY: 'auto' }}>
        {loading && (
          <Box sx={{ py: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={30} thickness={4.5} />
            <Typography className="mono-label" sx={{ color: 'text.secondary' }}>
              Fetching remote file
            </Typography>
          </Box>
        )}

        {!loading && error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}

        {!loading && !error && kind === 'csv' && (
          csvRows.length ? (
            <Box>
              <TableContainer
                sx={{
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                  maxHeight: 460,
                }}
              >
                <Table size="small" stickyHeader sx={tableSx}>
                  <TableHead>
                    <TableRow>
                      {csvRows[0].map((header, index) => (
                        <TableCell key={`${header}-${index}`}>{header || `Column ${index + 1}`}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {visibleRows.slice(1).map((row, rowIndex) => (
                      <TableRow
                        key={rowIndex}
                        sx={{
                          backgroundColor:
                            rowIndex % 2 === 1 ? alpha(theme.palette.text.primary, isDark ? 0.035 : 0.018) : 'transparent',
                        }}
                      >
                        {csvRows[0].map((_, cellIndex) => (
                          <TableCell key={cellIndex}>{row[cellIndex] ?? ''}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {hiddenRowCount > 0 && (
                <Stack direction="row" spacing={1.5} sx={{ mt: 1.5, alignItems: 'center' }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                    {hiddenRowCount} more {hiddenRowCount === 1 ? 'row' : 'rows'} not shown.
                  </Typography>
                  <Button size="small" onClick={() => setShowAllRows(true)}>
                    Show all
                  </Button>
                </Stack>
              )}
            </Box>
          ) : (
            <Alert severity="info">The file is empty or contains no tabular rows.</Alert>
          )
        )}

        {!loading && !error && (kind === 'json' || kind === 'text') && (
          <Box
            sx={{
              border: `1px solid ${panel.border}`,
              borderRadius: 2.5,
              overflow: 'hidden',
              backgroundColor: panel.bg,
            }}
          >
            {/* Window chrome */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.75,
                px: 1.5,
                py: 0.85,
                backgroundColor: panel.chromeBg,
                borderBottom: `1px solid ${panel.border}`,
              }}
            >
              {['#ff5f57', '#febc2e', '#28c840'].map((dot) => (
                <Box
                  key={dot}
                  aria-hidden
                  sx={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: dot, opacity: 0.8 }}
                />
              ))}
              <Typography
                sx={{
                  ml: 'auto',
                  fontFamily: theme.typography.fontFamilyCode,
                  fontSize: '0.6rem',
                  letterSpacing: '0.16em',
                  color: panel.chromeText,
                  textTransform: 'uppercase',
                }}
              >
                {kind === 'json' ? 'json · formatted' : 'raw · read-only'}
              </Typography>
            </Box>

            <Box
              component="pre"
              sx={{
                m: 0,
                p: 2,
                maxHeight: 460,
                overflow: 'auto',
                fontFamily: theme.typography.fontFamilyCode,
                fontSize: '0.78rem',
                lineHeight: 1.7,
                color: panel.text,
                whiteSpace: kind === 'json' ? 'pre' : 'pre-wrap',
                wordBreak: kind === 'json' ? 'normal' : 'break-word',
              }}
            >
              {kind === 'json' ? jsonText : rawContent}
            </Box>
          </Box>
        )}

        {!loading && !error && kind === 'file' && (
          <Box sx={{ py: 8, textAlign: 'center' }}>
            <Box
              sx={{
                width: 54,
                height: 54,
                mx: 'auto',
                mb: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 2.5,
                border: '1px solid',
                borderColor: 'divider',
                color: 'text.disabled',
                '& svg': { fontSize: 26 },
              }}
            >
              <InsertDriveFileRounded />
            </Box>
            <Typography sx={{ fontWeight: 600, mb: 0.5 }}>Preview not available</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2.5 }}>
              This file type cannot be rendered in the browser.
            </Typography>
            <Button variant="outlined" startIcon={<DownloadRounded />} onClick={handleDownload}>
              Download file
            </Button>
          </Box>
        )}
      </DialogContent>

      <Divider />

      <DialogActions sx={{ px: 2.5, py: 1.5, gap: 1 }}>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Copy file content" arrow>
          <span>
            <Button
              size="small"
              startIcon={<ContentCopyRounded fontSize="small" />}
              onClick={handleCopy}
              disabled={loading || !rawContent}
            >
              Copy
            </Button>
          </span>
        </Tooltip>
        <Button
          size="small"
          variant="contained"
          startIcon={<DownloadRounded fontSize="small" />}
          onClick={handleDownload}
          disabled={loading || !rawContent}
        >
          Download
        </Button>
      </DialogActions>
    </Dialog>
  );
}
