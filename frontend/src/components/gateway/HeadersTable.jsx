import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  IconButton,
  InputAdornment,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Check, ContentCopy, FilterAltOff, Search } from '@mui/icons-material';
import { alpha, useTheme } from '@mui/material/styles';

/* ------------------------------------------------------------------ */
/*  Private helpers                                                    */
/* ------------------------------------------------------------------ */

/** Normalise headers into `[{ name, value }]` from object / array forms. */
function toEntries(headers) {
  if (!headers) return [];

  if (Array.isArray(headers)) {
    return headers
      .map((entry) => {
        if (Array.isArray(entry)) return { name: String(entry[0] ?? ''), value: entry[1] };
        if (entry && typeof entry === 'object') {
          return { name: String(entry.key ?? entry.name ?? ''), value: entry.value };
        }
        return null;
      })
      .filter((entry) => entry && entry.name);
  }

  if (typeof headers === 'object') {
    return Object.entries(headers).map(([name, value]) => ({ name, value }));
  }

  return [];
}

/** Render any header value as a display string. */
function toDisplayValue(value) {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

/** Clipboard write with a legacy fallback; resolves to true on success. */
async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    const helper = document.createElement('textarea');
    helper.value = text;
    helper.style.position = 'fixed';
    helper.style.opacity = '0';
    document.body.appendChild(helper);
    helper.select();
    document.execCommand('copy');
    document.body.removeChild(helper);
    return true;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

/**
 * Reusable key/value audit table for request & response headers.
 *
 * - Striped rows, monospace values, click-to-copy on every row.
 * - "Copy JSON" button exports the whole set.
 * - Name filter appears once the set is long enough to need it.
 *
 * Consumed by the Gateway response inspector and the Logs detail view.
 */
export default function HeadersTable({
  headers,
  title,
  emptyMessage = 'No headers captured for this stage.',
  maxHeight = 320,
}) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const codeFont = theme.typography.fontFamilyCode;

  const [query, setQuery] = useState('');
  const [copiedKey, setCopiedKey] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  const entries = useMemo(() => toEntries(headers), [headers]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return entries;
    return entries.filter((entry) => entry.name.toLowerCase().includes(needle));
  }, [entries, query]);

  const flash = useCallback((key) => {
    setCopiedKey(key);
    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setCopiedKey(null), 1500);
  }, []);

  const handleCopyValue = useCallback(
    async (entry, key) => {
      const ok = await copyText(toDisplayValue(entry.value));
      if (ok) flash(key);
    },
    [flash]
  );

  const handleCopyAll = useCallback(async () => {
    const asObject = {};
    entries.forEach((entry) => {
      asObject[entry.name] = entry.value;
    });
    const ok = await copyText(JSON.stringify(asObject, null, 2));
    if (ok) flash('__all__');
  }, [entries, flash]);

  const stripe = alpha(theme.palette.text.primary, isDark ? 0.028 : 0.018);

  const headCellSx = {
    fontFamily: codeFont,
    fontSize: '0.58rem',
    fontWeight: 500,
    letterSpacing: '0.14em',
    textTransform: 'uppercase',
    color: 'text.disabled',
    py: 0.75,
    borderColor: 'divider',
    backgroundColor: alpha(theme.palette.background.paper, 0.97),
  };

  if (entries.length === 0) {
    return (
      <Box>
        {title ? (
          <Typography className="mono-label" sx={{ color: 'text.disabled', mb: 0.75 }}>
            {title}
          </Typography>
        ) : null}
        <Box
          sx={{
            py: 2.25,
            px: 2,
            borderRadius: 2,
            border: '1px dashed',
            borderColor: 'divider',
            textAlign: 'center',
          }}
        >
          <Typography variant="body2" sx={{ color: 'text.disabled', fontStyle: 'italic' }}>
            {emptyMessage}
          </Typography>
        </Box>
      </Box>
    );
  }

  return (
    <Box>
      {/* Toolbar ------------------------------------------------------ */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        {title ? (
          <Typography className="mono-label" sx={{ color: 'text.disabled' }}>
            {title}
          </Typography>
        ) : null}
        <Chip
          label={entries.length}
          size="small"
          sx={{
            height: 19,
            fontFamily: codeFont,
            fontSize: '0.62rem',
            fontWeight: 600,
            color: 'text.secondary',
            backgroundColor: alpha(theme.palette.text.primary, isDark ? 0.08 : 0.05),
          }}
        />
        <Box sx={{ flex: 1 }} />

        {entries.length > 4 ? (
          <TextField
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            size="small"
            placeholder="Filter by name"
            aria-label="Filter headers by name"
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <Search sx={{ fontSize: 16, color: 'text.disabled' }} />
                  </InputAdornment>
                ),
                endAdornment: query ? (
                  <InputAdornment position="end">
                    <IconButton
                      size="small"
                      edge="end"
                      aria-label="Clear filter"
                      onClick={() => setQuery('')}
                    >
                      <FilterAltOff sx={{ fontSize: 14 }} />
                    </IconButton>
                  </InputAdornment>
                ) : null,
              },
            }}
            sx={{ width: 188, '& input': { fontSize: '0.72rem', py: 0.55 } }}
          />
        ) : null}

        <Tooltip title="Copy all as JSON">
          <Button
            size="small"
            onClick={handleCopyAll}
            startIcon={
              copiedKey === '__all__' ? (
                <Check sx={{ fontSize: 15 }} />
              ) : (
                <ContentCopy sx={{ fontSize: 14 }} />
              )
            }
            sx={{
              minWidth: 0,
              px: 1.1,
              py: 0.35,
              fontSize: '0.68rem',
              color: copiedKey === '__all__' ? 'success.main' : 'text.secondary',
            }}
          >
            {copiedKey === '__all__' ? 'Copied' : 'Copy JSON'}
          </Button>
        </Tooltip>
      </Box>

      {/* Table --------------------------------------------------------- */}
      <TableContainer
        sx={{
          maxHeight,
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
          backgroundColor: alpha(theme.palette.background.paper, isDark ? 0.4 : 1),
        }}
      >
        <Table size="small" stickyHeader sx={{ '& td, & th': { borderColor: 'divider' } }}>
          <TableHead>
            <TableRow>
              <TableCell sx={{ ...headCellSx, width: '32%', minWidth: 150 }}>Header</TableCell>
              <TableCell sx={headCellSx}>Value</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filtered.map((entry, index) => {
              const rowKey = `${index}:${entry.name}`;
              const copied = copiedKey === rowKey;
              return (
                <TableRow
                  key={rowKey}
                  hover
                  onClick={() => handleCopyValue(entry, rowKey)}
                  sx={{
                    cursor: 'copy',
                    '&:nth-of-type(odd)': { backgroundColor: stripe },
                    '&:last-child td': { borderBottom: 0 },
                  }}
                >
                  <TableCell
                    sx={{
                      verticalAlign: 'top',
                      py: 0.65,
                      fontFamily: codeFont,
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      wordBreak: 'break-word',
                    }}
                  >
                    {entry.name}
                  </TableCell>
                  <TableCell sx={{ py: 0.5 }}>
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
                      <Typography
                        component="span"
                        sx={{
                          flex: 1,
                          minWidth: 0,
                          fontFamily: codeFont,
                          fontSize: '0.72rem',
                          lineHeight: 1.65,
                          color: 'text.secondary',
                          wordBreak: 'break-all',
                        }}
                      >
                        {toDisplayValue(entry.value) || '—'}
                      </Typography>
                      <Tooltip title={copied ? 'Copied' : 'Copy value'}>
                        <IconButton
                          size="small"
                          aria-label={`Copy ${entry.name}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            handleCopyValue(entry, rowKey);
                          }}
                          sx={{
                            mt: -0.2,
                            mr: -0.4,
                            opacity: copied ? 1 : 0.35,
                            transition: 'opacity 0.15s ease',
                            '&:hover': { opacity: 1 },
                          }}
                        >
                          {copied ? (
                            <Check sx={{ fontSize: 14, color: 'success.main' }} />
                          ) : (
                            <ContentCopy sx={{ fontSize: 13 }} />
                          )}
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {filtered.length === 0 ? (
        <Typography variant="caption" sx={{ display: 'block', mt: 1, color: 'text.disabled' }}>
          No headers match “{query}”.
        </Typography>
      ) : null}
    </Box>
  );
}
