import { useCallback, useState } from 'react';
import { Box, Card, Chip, IconButton, Tooltip, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { DeleteSweep, History } from '@mui/icons-material';
import { useQueryClient } from '@tanstack/react-query';

import GatewayTester from '../components/gateway/GatewayTester';
import ResponseViewer from '../components/gateway/ResponseViewer';
import MethodChip from '../components/common/MethodChip';
import StatusChip from '../components/common/StatusChip';
import { mapAndCall } from '../services/gatewayService';
import { useApiMutation } from '../hooks/useApi';

const HISTORY_LIMIT = 8;

function formatClock(timestamp) {
  if (!timestamp) return '';
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour12: false });
}

/** Never expose the raw session token in the header audit trail. */
function maskAuthorization(value) {
  const text = String(value ?? '');
  const [scheme] = text.split(' ');
  return /^bearer$/i.test(scheme) ? `${scheme} ••••••` : '••••••';
}

function extractErrorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg ?? JSON.stringify(item)).join(' · ');
  }
  if (typeof detail === 'string' && detail) return detail;
  if (detail != null) {
    try {
      return JSON.stringify(detail);
    } catch {
      /* fall through */
    }
  }
  return error?.message || 'The request could not be completed.';
}

/** Wrap a transport failure in the gateway response shape so the viewer can render it. */
function buildErrorResponse(error) {
  let requestHeaders = null;
  try {
    const raw = error?.config?.headers;
    const plain = typeof raw?.toJSON === 'function' ? raw.toJSON() : { ...(raw ?? {}) };
    const entries = Object.entries(plain);
    if (entries.length > 0) {
      requestHeaders = Object.fromEntries(
        entries.map(([name, value]) => [
          name,
          /^authorization$/i.test(name) ? maskAuthorization(value) : value,
        ])
      );
    }
  } catch {
    requestHeaders = null;
  }

  return {
    success: false,
    data: error?.response?.data ?? null,
    status_code: error?.response?.status ?? null,
    response_time_ms: null,
    request_headers: requestHeaders,
    response_headers: null,
    external_request_headers: null,
    external_response_headers: null,
    error: extractErrorMessage(error),
  };
}

/** One row in the recent-calls list. */
function HistoryRow({ entry, active, onSelect }) {
  const theme = useTheme();
  const code = entry.response?.status_code ?? null;
  const tone =
    code == null
      ? theme.palette.text.disabled
      : code < 300
        ? theme.palette.success.main
        : code < 400
          ? theme.palette.info.main
          : code < 500
            ? theme.palette.warning.main
            : theme.palette.error.main;
  const ok = entry.response?.success !== false && !entry.response?.error;

  return (
    <Box
      role="button"
      tabIndex={0}
      onClick={() => onSelect(entry)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect(entry);
        }
      }}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.25,
        px: 2.25,
        py: 1,
        cursor: 'pointer',
        borderTop: '1px solid',
        borderColor: 'divider',
        backgroundColor: active ? alpha(theme.palette.primary.main, 0.06) : 'transparent',
        transition: 'background-color 0.15s ease',
        '&:hover': { backgroundColor: alpha(theme.palette.primary.main, 0.045) },
      }}
    >
      <MethodChip method={entry.request?.targetMethod} size="small" />
      <Typography
        sx={{
          width: 44,
          flexShrink: 0,
          fontFamily: theme.typography.fontFamilyCode,
          fontSize: '0.75rem',
          fontWeight: 600,
          color: tone,
        }}
      >
        {code ?? '—'}
      </Typography>
      <Typography
        variant="body2"
        noWrap
        sx={{
          flex: 1,
          minWidth: 0,
          fontFamily: theme.typography.fontFamilyCode,
          fontSize: '0.73rem',
          color: 'text.secondary',
        }}
      >
        {entry.request?.targetUrl}
      </Typography>
      <Typography
        sx={{
          flexShrink: 0,
          display: { xs: 'none', sm: 'block' },
          fontFamily: theme.typography.fontFamilyCode,
          fontSize: '0.68rem',
          color: 'text.disabled',
        }}
      >
        {entry.response?.response_time_ms != null ? `${entry.response.response_time_ms} ms` : '—'}
      </Typography>
      <Typography
        sx={{
          flexShrink: 0,
          display: { xs: 'none', md: 'block' },
          fontFamily: theme.typography.fontFamilyCode,
          fontSize: '0.68rem',
          color: 'text.disabled',
        }}
      >
        {formatClock(entry.timestamp)}
      </Typography>
      <StatusChip status={ok ? 'success' : 'failed'} size="small" />
    </Box>
  );
}

/**
 * Gateway tester — compose a mapped request on the left, inspect the full
 * request / response trail (including every exchanged header) on the right.
 */
export default function GatewayPage() {
  const theme = useTheme();
  const queryClient = useQueryClient();

  const [activeCall, setActiveCall] = useState(null);
  const [history, setHistory] = useState([]);

  const sendMutation = useApiMutation(mapAndCall, {
    onSuccess: () => {
      // A gateway call is logged server-side; refresh the Logs views.
      queryClient.invalidateQueries({ queryKey: ['logs'] });
    },
  });
  const loading = sendMutation.isPending;

  const handleSend = useCallback(
    async (payload) => {
      const stamp = new Date();
      let response;
      try {
        response = await sendMutation.mutateAsync(payload);
      } catch (error) {
        response = buildErrorResponse(error);
      }
      const call = {
        id: stamp.getTime(),
        request: payload,
        response,
        timestamp: stamp,
      };
      setActiveCall(call);
      setHistory((prev) => [call, ...prev].slice(0, HISTORY_LIMIT));
    },
    [sendMutation]
  );

  return (
    <Box>
      {/* Page header -------------------------------------------------- */}
      <Box sx={{ mb: 2.5 }}>
        <Typography className="mono-label" sx={{ color: 'text.disabled' }}>
          Gateway · Live runner
        </Typography>
        <Typography variant="h5" sx={{ mt: 0.5 }}>
          Exercise mappings against the real target
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.75, maxWidth: 780 }}>
          Compose a request, run it through the mapping engine and inspect every header that crossed
          the wire — from this console to the gateway and from the gateway to the upstream API.
        </Typography>
      </Box>

      {/* Two-panel workbench ------------------------------------------ */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 10fr) minmax(0, 11fr)' },
          gap: 2.5,
          alignItems: 'start',
        }}
      >
        <GatewayTester onSend={handleSend} loading={loading} />

        <Box sx={{ minWidth: 0, position: { lg: 'sticky' }, top: { lg: 0 } }}>
          <ResponseViewer
            result={activeCall?.response ?? null}
            request={activeCall?.request ?? null}
            timestamp={activeCall?.timestamp ?? null}
            callId={activeCall?.id ?? null}
            loading={loading}
          />
        </Box>
      </Box>

      {/* Recent calls -------------------------------------------------- */}
      {history.length > 0 ? (
        <Card
          elevation={0}
          sx={{ mt: 2.5, borderRadius: 3, border: '1px solid', borderColor: 'divider', overflow: 'hidden' }}
        >
          <Box
            sx={{
              px: 2.25,
              py: 1.4,
              display: 'flex',
              alignItems: 'center',
              gap: 1.25,
              borderBottom: '1px solid',
              borderColor: 'divider',
            }}
          >
            <History sx={{ fontSize: 18, color: 'text.secondary' }} />
            <Typography className="mono-label" sx={{ color: 'text.secondary' }}>
              Recent calls
            </Typography>
            <Chip
              label={history.length}
              size="small"
              sx={{
                height: 19,
                fontSize: '0.62rem',
                fontWeight: 600,
                fontFamily: theme.typography.fontFamilyCode,
                color: 'text.secondary',
                backgroundColor: alpha(theme.palette.text.primary, 0.06),
              }}
            />
            <Box sx={{ flex: 1 }} />
            <Tooltip title="Clear history">
              <IconButton
                size="small"
                aria-label="Clear history"
                onClick={() => setHistory([])}
                sx={{ color: 'text.disabled', '&:hover': { color: 'error.main' } }}
              >
                <DeleteSweep fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>

          {history.map((entry) => (
            <HistoryRow
              key={entry.id}
              entry={entry}
              active={activeCall?.id === entry.id}
              onSelect={setActiveCall}
            />
          ))}
        </Card>
      ) : null}
    </Box>
  );
}
