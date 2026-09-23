import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  IconButton,
  InputAdornment,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TablePagination,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Download, FilterAltOff, Refresh, Search, Tune } from '@mui/icons-material';
import { alpha, useTheme } from '@mui/material/styles';
import { keepPreviousData } from '@tanstack/react-query';

import { useApiQuery } from '../hooks/useApi';
import logService from '../services/logService';
import endpointService from '../services/endpointService';
import { useSnackbar } from '../context/SnackbarContext';
import LogsTable from '../components/logs/LogsTable';

const EMPTY_FILTERS = {
  endpoint_id: '',
  status: '',
  method: '',
  path: '',
  date_from: '',
  date_to: '',
};

const PAGE_SIZES = [10, 25, 50, 100];
const METHOD_OPTIONS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];
const STATUS_OPTIONS = ['SUCCESS', 'FAILED'];
const AUTO_REFRESH_MS = 30_000;

/**
 * Call logs page — filter bar, paginated audit table and JSON export.
 *
 * The table stays mounted while filters change (React Query
 * `keepPreviousData`), so pagination never flashes an empty state.
 */
export default function LogsPage() {
  const theme = useTheme();
  const { showSnackbar } = useSnackbar();

  const [draft, setDraft] = useState(EMPTY_FILTERS); // being edited
  const [applied, setApplied] = useState(EMPTY_FILTERS); // currently queried
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [exporting, setExporting] = useState(false);

  /* ---------------- data ---------------- */

  const endpointsQuery = useApiQuery(['endpoints'], () => endpointService.getEndpoints(), {
    staleTime: 5 * 60_000,
  });

  const endpointOptions = useMemo(() => {
    const data = endpointsQuery.data;
    const list = Array.isArray(data) ? data : data?.items ?? [];
    return list.map((endpoint) => ({
      id: endpoint.id,
      label: endpoint.endpoint_code || `endpoint ${String(endpoint.id).slice(0, 8)}`,
    }));
  }, [endpointsQuery.data]);

  const requestParams = useMemo(() => {
    const params = { page, per_page: perPage };
    if (applied.endpoint_id) params.endpoint_id = applied.endpoint_id;
    if (applied.status) params.status = applied.status;
    if (applied.method) params.method = applied.method;
    if (applied.path) params.path = applied.path;
    if (applied.date_from) params.date_from = `${applied.date_from}T00:00:00`;
    if (applied.date_to) params.date_to = `${applied.date_to}T23:59:59`;
    return params;
  }, [applied, page, perPage]);

  const logsQuery = useApiQuery(
    ['call-logs', requestParams],
    () => logService.getLogs(requestParams),
    {
      placeholderData: keepPreviousData,
      refetchInterval: autoRefresh ? AUTO_REFRESH_MS : false,
    }
  );

  const logs = logsQuery.data?.items ?? [];
  const total = logsQuery.data?.total ?? 0;
  const totalPages = logsQuery.data?.pages ?? 0;
  const isLoading = logsQuery.isLoading;
  const isRefreshing = logsQuery.isFetching && !isLoading;

  // Display-only clamp: keeps the pager sane if the result set ever shrinks
  // below the requested page (derived value, never set during render).
  const currentPage = totalPages > 0 ? Math.min(page, totalPages) : page;

  /* ---------------- handlers ---------------- */

  const updateDraft = (key, value) => setDraft((prev) => ({ ...prev, [key]: value }));

  const activeFilterCount = useMemo(
    () => Object.values(applied).filter((value) => value !== '').length,
    [applied]
  );

  const applyFilters = () => {
    if (draft.date_from && draft.date_to && draft.date_from > draft.date_to) {
      showSnackbar('The “From” date must be before the “To” date.', 'warning');
      return;
    }
    setApplied({ ...draft, path: draft.path.trim() });
    setPage(1);
    setExpandedId(null);
  };

  const clearFilters = () => {
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setPage(1);
    setExpandedId(null);
  };

  const toggleExpand = (id) => setExpandedId((prev) => (prev === id ? null : id));

  const handleExport = async () => {
    setExporting(true);
    try {
      const exported = await logService.getLogs({ ...requestParams, page: 1, per_page: 1000 });
      const items = exported?.items ?? [];
      const payload = {
        exported_at: new Date().toISOString(),
        filters: applied,
        total: exported?.total ?? items.length,
        count: items.length,
        logs: items,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `call-logs-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      showSnackbar(
        `Exported ${items.length} log ${items.length === 1 ? 'entry' : 'entries'}.`,
        'success'
      );
    } catch (error) {
      showSnackbar(
        error?.response?.data?.detail || error?.message || 'Export failed.',
        'error'
      );
    } finally {
      setExporting(false);
    }
  };

  const queryError = logsQuery.isError
    ? logsQuery.error?.response?.data?.detail || logsQuery.error?.message
    : null;

  /* ---------------- render ---------------- */

  const fieldSx = { minWidth: 0 };

  return (
    <Box>
      {/* ---------- page header ---------- */}
      <Box
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-start',
          gap: 2,
          mb: 2.5,
        }}
      >
        <Box sx={{ flex: '1 1 340px', minWidth: 0 }}>
          <Typography className="mono-label" sx={{ color: 'primary.main', mb: 0.75 }}>
            Observability · Full request audit
          </Typography>
          <Typography variant="h5" sx={{ mb: 0.5 }}>
            Call Logs
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', maxWidth: 660 }}>
            Every proxied call with its internal and upstream headers, bodies, query
            parameters, response timing and the full diagnostic log.
          </Typography>
        </Box>

        <Stack
          direction="row"
          spacing={1}
          useFlexGap
          sx={{ alignItems: 'center', flexWrap: 'wrap' }}
        >
          <Tooltip title="Refresh now" arrow>
            <span>
              <IconButton
                onClick={() => logsQuery.refetch()}
                aria-label="Refresh now"
                sx={{
                  height: 40,
                  width: 40,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 2,
                  color: 'text.secondary',
                }}
              >
                <Refresh sx={{ fontSize: 19 }} />
              </IconButton>
            </span>
          </Tooltip>

          <Box
            sx={{
              height: 40,
              display: 'flex',
              alignItems: 'center',
              px: 1.25,
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 2,
            }}
          >
            <FormControlLabel
              sx={{ m: 0 }}
              control={
                <Switch
                  size="small"
                  checked={autoRefresh}
                  onChange={(event) => {
                    setAutoRefresh(event.target.checked);
                    if (event.target.checked) logsQuery.refetch();
                  }}
                />
              }
              label={
                <Typography className="mono-label" sx={{ fontSize: '0.55rem', ml: 0.25 }}>
                  Auto · 30s
                </Typography>
              }
            />
          </Box>

          <Button
            variant="outlined"
            onClick={handleExport}
            disabled={exporting}
            startIcon={
              exporting ? (
                <CircularProgress size={15} thickness={5} color="inherit" />
              ) : (
                <Download sx={{ fontSize: 18 }} />
              )
            }
            sx={{ height: 40 }}
          >
            Export JSON
          </Button>
        </Stack>
      </Box>

      {/* ---------- filter bar ---------- */}
      <Paper
        elevation={0}
        sx={{
          p: 2,
          borderRadius: 3,
          border: '1px solid',
          borderColor: 'divider',
          backgroundColor: alpha(theme.palette.background.paper, 0.72),
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap' }}>
          <Tune sx={{ fontSize: 17, color: 'text.disabled' }} />
          <Typography className="mono-label" sx={{ color: 'text.secondary' }}>
            Filters
          </Typography>
          {activeFilterCount > 0 ? (
            <Chip
              size="small"
              label={activeFilterCount}
              sx={{
                height: 20,
                fontFamily: theme.typography.fontFamilyCode,
                fontSize: '0.64rem',
                color: 'primary.main',
                backgroundColor: alpha(theme.palette.primary.main, 0.1),
                border: `1px solid ${alpha(theme.palette.primary.main, 0.3)}`,
                '& .MuiChip-label': { px: 0.9 },
              }}
            />
          ) : null}
          <Box sx={{ flex: 1 }} />
          <Button
            size="small"
            color="inherit"
            onClick={clearFilters}
            disabled={activeFilterCount === 0}
            startIcon={<FilterAltOff sx={{ fontSize: 16 }} />}
            sx={{ color: 'text.secondary' }}
          >
            Clear filters
          </Button>
        </Box>

        <Box
          sx={{
            display: 'grid',
            gap: 1.5,
            mt: 1.75,
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(0, 1fr))',
              md: 'repeat(3, minmax(0, 1fr))',
              xl: 'repeat(6, minmax(0, 1fr))',
            },
          }}
        >
          <TextField
            select
            size="small"
            label="Endpoint"
            sx={fieldSx}
            value={draft.endpoint_id}
            onChange={(event) => updateDraft('endpoint_id', event.target.value)}
          >
            <MenuItem value="">All endpoints</MenuItem>
            {endpointOptions.map((option) => (
              <MenuItem key={option.id} value={option.id}>
                {option.label}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            select
            size="small"
            label="Status"
            sx={fieldSx}
            value={draft.status}
            onChange={(event) => updateDraft('status', event.target.value)}
          >
            <MenuItem value="">All statuses</MenuItem>
            {STATUS_OPTIONS.map((status) => (
              <MenuItem key={status} value={status}>
                {status}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            select
            size="small"
            label="Method"
            sx={fieldSx}
            value={draft.method}
            onChange={(event) => updateDraft('method', event.target.value)}
          >
            <MenuItem value="">All methods</MenuItem>
            {METHOD_OPTIONS.map((method) => (
              <MenuItem key={method} value={method}>
                {method}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            size="small"
            type="date"
            label="From"
            sx={fieldSx}
            value={draft.date_from}
            onChange={(event) => updateDraft('date_from', event.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />

          <TextField
            size="small"
            type="date"
            label="To"
            sx={fieldSx}
            value={draft.date_to}
            onChange={(event) => updateDraft('date_to', event.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />

          <TextField
            size="small"
            label="Search by path"
            placeholder="/orders/create"
            sx={fieldSx}
            value={draft.path}
            onChange={(event) => updateDraft('path', event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') applyFilters();
            }}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <Search sx={{ fontSize: 17, color: 'text.disabled' }} />
                  </InputAdornment>
                ),
              },
            }}
          />
        </Box>

        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
          <Button variant="contained" onClick={applyFilters} startIcon={<Tune sx={{ fontSize: 17 }} />}>
            Apply filters
          </Button>
        </Box>
      </Paper>

      {queryError ? (
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => logsQuery.refetch()}>
              Retry
            </Button>
          }
        >
          {typeof queryError === 'string' ? queryError : 'Failed to load call logs.'}
        </Alert>
      ) : null}

      {/* ---------- results ---------- */}
      <Paper
        elevation={0}
        sx={{
          mt: 2,
          borderRadius: 3,
          border: '1px solid',
          borderColor: 'divider',
          overflow: 'hidden',
        }}
      >
        <Box
          sx={{
            px: 2,
            py: 1.5,
            display: 'flex',
            alignItems: 'center',
            gap: 1.25,
            borderBottom: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle2">Call history</Typography>
          <Chip
            size="small"
            label={`${total.toLocaleString('en-US')} ${total === 1 ? 'call' : 'calls'}`}
            sx={{
              height: 22,
              fontFamily: theme.typography.fontFamilyCode,
              fontSize: '0.64rem',
              color: 'text.secondary',
              backgroundColor: alpha(theme.palette.text.primary, 0.05),
              border: '1px solid',
              borderColor: 'divider',
              '& .MuiChip-label': { px: 1 },
            }}
          />
          <Box sx={{ flex: 1 }} />
          {isRefreshing ? (
            <Typography
              className="mono-label"
              sx={{
                color: 'text.disabled',
                fontSize: '0.55rem',
                animation: 'pulse 1.4s ease-in-out infinite',
                '@keyframes pulse': {
                  '0%, 100%': { opacity: 0.45 },
                  '50%': { opacity: 1 },
                },
              }}
            >
              Syncing…
            </Typography>
          ) : null}
        </Box>

        <LogsTable
          logs={logs}
          loading={isLoading}
          refreshing={isRefreshing}
          expandedId={expandedId}
          onToggleExpand={toggleExpand}
        />

        <TablePagination
          component="div"
          count={total}
          page={Math.max(currentPage - 1, 0)}
          onPageChange={(_event, next) => {
            setPage(next + 1);
            setExpandedId(null);
          }}
          rowsPerPage={perPage}
          onRowsPerPageChange={(event) => {
            setPerPage(Number.parseInt(event.target.value, 10));
            setPage(1);
            setExpandedId(null);
          }}
          rowsPerPageOptions={PAGE_SIZES}
          showFirstButton
          showLastButton
          labelRowsPerPage="Rows per page"
          labelDisplayedRows={({ from, to, count }) =>
            `${from}–${to} of ${count !== -1 ? count : `more than ${to}`}`
          }
          sx={{
            borderTop: '1px solid',
            borderColor: 'divider',
            '.MuiTablePagination-toolbar': { minHeight: 52 },
            '.MuiTablePagination-selectLabel, .MuiTablePagination-displayedRows': {
              fontFamily: theme.typography.fontFamilyCode,
              fontSize: '0.72rem',
              color: 'text.secondary',
            },
          }}
        />
      </Paper>
    </Box>
  );
}
