import { Chip } from '@mui/material';
import { alpha, lighten, useTheme } from '@mui/material/styles';

/**
 * HTTP method palette — crisp, console-style chips.
 * GET=green · POST=blue · PUT=orange · DELETE=red · PATCH=purple
 */
export const METHOD_COLORS = {
  GET: '#2e7d32',
  POST: '#1976d2',
  PUT: '#ed6c02',
  PATCH: '#9c27b0',
  DELETE: '#d32f2f',
  HEAD: '#546e7a',
  OPTIONS: '#546e7a',
};

export default function MethodChip({ method = 'GET', size = 'small', sx, ...rest }) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const label = String(method || 'GET').toUpperCase();
  const base = METHOD_COLORS[label] || '#546e7a';
  const textColor = isDark ? lighten(base, 0.42) : base;

  return (
    <Chip
      label={label}
      size={size}
      sx={{
        fontFamily: theme.typography.fontFamilyCode,
        fontSize: '0.68rem',
        fontWeight: 600,
        letterSpacing: '0.05em',
        height: 24,
        borderRadius: '7px',
        color: textColor,
        backgroundColor: alpha(base, isDark ? 0.18 : 0.1),
        border: `1px solid ${alpha(base, isDark ? 0.45 : 0.3)}`,
        '& .MuiChip-label': { px: 1.1 },
        ...sx,
      }}
      {...rest}
    />
  );
}
