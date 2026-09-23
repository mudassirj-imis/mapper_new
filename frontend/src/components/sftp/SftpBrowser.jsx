import { useMemo, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from '@mui/material';
import {
  ChevronRightRounded,
  DataObjectRounded,
  DescriptionRounded,
  FolderOffRounded,
  FolderRounded,
  InsertDriveFileRounded,
  TableViewRounded,
} from '@mui/icons-material';
import { alpha, lighten, useTheme } from '@mui/material/styles';

/**
 * Remote directory listing with sortable columns and a path breadcrumb.
 *
 * Props:
 *   files        raw listing payload — accepts an array or { files|entries|items }
 *   currentPath  remote directory currently displayed
 *   onNavigate   (path) => void — breadcrumb / folder activation
 *   onPreview    (file) => void — file activation (double-click)
 *   loading      renders shimmering skeleton rows
 */

const TEXT_EXTENSIONS = new Set([
  'txt', 'log', 'md', 'xml', 'yml', 'yaml', 'ini', 'conf', 'env', 'sql',
  'html', 'htm', 'js', 'ts', 'tsx', 'jsx', 'py', 'java', 'go', 'rs', 'sh', 'bat', 'ps1',
]);

const KIND_META = {
  folder: { label: 'Folder', Icon: FolderRounded, color: '#e8a200' },
  csv: { label: 'CSV', Icon: TableViewRounded, color: '#2e7d32' },
  json: { label: 'JSON', Icon: DataObjectRounded, color: '#1976d2' },
  text: { label: 'Text', Icon: DescriptionRounded, color: '#9c27b0' },
  file: { label: 'File', Icon: InsertDriveFileRounded, color: '#546e7a' },
};

/* ------------------------------- helpers ------------------------------- */

const joinPath = (base, name) => {
  const cleanBase = String(base || '/').replace(/[\\/]+$/, '');
  const cleanName = String(name || '').replace(/^[\\/]+/, '');
  if (!cleanName) return cleanBase || '/';
  return `${cleanBase}/${cleanName}`.replace(/\/{2,}/g, '/');
};

const resolveKind = (file) => {
  if (file.isDir) return 'folder';
  const parts = String(file.name || '').split('.');
  const ext = parts.length > 1 ? parts.pop().toLowerCase() : '';
  if (ext === 'csv' || ext === 'tsv') return 'csv';
  if (ext === 'json') return 'json';
  if (TEXT_EXTENSIONS.has(ext)) return 'text';
  return 'file';
};

const normalizeEntries = (files) => {
  const list = Array.isArray(files)
    ? files
    : files?.files ?? files?.entries ?? files?.items ?? [];

  return list
    .map((item) => {
      const rawType = String(item?.type ?? '').toLowerCase();
      return {
        name: String(item?.name ?? item?.filename ?? item?.file_name ?? ''),
        isDir: Boolean(
          item?.is_dir ??
            item?.is_directory ??
            item?.isDir ??
            (rawType === 'dir' || rawType === 'directory')
        ),
        size: Number(item?.size ?? item?.file_size ?? 0) || 0,
        modified: item?.modified ?? item?.modified_at ?? item?.mtime ?? item?.updated_at ?? null,
      };
    })
    .filter((item) => item.name);
};

const formatBytes = (bytes) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${index === 0 || value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
};

const formatDate = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

/* ------------------------------ component ------------------------------ */

export default function SftpBrowser({
  files,
  currentPath = '/',
  onNavigate,
  onPreview,
  loading = false,
}) {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const [orderBy, setOrderBy] = useState('name');
  const [orderDir, setOrderDir] = useState('asc');
  const [selected, setSelected] = useState(null);

  const entries = useMemo(() => normalizeEntries(files), [files]);

  const sorted = useMemo(() => {
    const direction = orderDir === 'asc' ? 1 : -1;
    return [...entries].sort((a, b) => {
      // Folders always stay grouped above files.
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;

      if (orderBy === 'size') return ((a.size || 0) - (b.size || 0)) * direction;
      if (orderBy === 'modified') {
        const aTime = a.modified ? new Date(a.modified).getTime() || 0 : 0;
        const bTime = b.modified ? new Date(b.modified).getTime() || 0 : 0;
        return (aTime - bTime) * direction;
      }
      if (orderBy === 'kind') {
        return KIND_META[resolveKind(a)].label.localeCompare(KIND_META[resolveKind(b)].label) * direction;
      }
      return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }) * direction;
    });
  }, [entries, orderBy, orderDir]);

  const crumbs = useMemo(() => {
    const parts = String(currentPath || '/').split(/[\\/]+/).filter(Boolean);
    const accumulated = [];
    return parts.map((part) => {
      accumulated.push(part);
      return { label: part, path: `/${accumulated.join('/')}` };
    });
  }, [currentPath]);

  const requestSort = (prop) => {
    if (orderBy === prop) {
      setOrderDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setOrderBy(prop);
      setOrderDir('asc');
    }
  };

  const activate = (entry) => {
    if (entry.isDir) onNavigate?.(joinPath(currentPath, entry.name));
    else onPreview?.(entry);
  };

  const stripe = alpha(theme.palette.text.primary, isDark ? 0.035 : 0.018);
  const hoverTint = alpha(theme.palette.primary.main, isDark ? 0.1 : 0.05);
  const selectedTint = alpha(theme.palette.primary.main, isDark ? 0.16 : 0.09);

  const columns = [
    { id: 'name', label: 'Name', align: 'left' },
    { id: 'kind', label: 'Type', align: 'left', hideBelow: 'sm' },
    { id: 'size', label: 'Size', align: 'right', hideBelow: 'sm' },
    { id: 'modified', label: 'Modified', align: 'right', hideBelow: 'md' },
  ];

  return (
    <Box>
      {/* Breadcrumb */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.25,
          px: 1.5,
          py: 1,
          mb: 1.5,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          backgroundColor: alpha(theme.palette.text.primary, isDark ? 0.03 : 0.015),
          overflowX: 'auto',
          whiteSpace: 'nowrap',
          '&::-webkit-scrollbar': { height: 4 },
        }}
      >
        <Button
          size="small"
          onClick={() => onNavigate?.('/')}
          startIcon={<FolderRounded sx={{ fontSize: 15 }} />}
          sx={{
            minWidth: 0,
            px: 1,
            py: 0.25,
            fontFamily: theme.typography.fontFamilyCode,
            fontSize: '0.72rem',
            color: currentPath === '/' ? 'text.primary' : 'text.secondary',
          }}
        >
          root
        </Button>

        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <Box key={crumb.path} sx={{ display: 'inline-flex', alignItems: 'center' }}>
              <ChevronRightRounded sx={{ fontSize: 15, color: 'text.disabled' }} />
              {isLast ? (
                <Typography
                  sx={{
                    px: 1,
                    fontFamily: theme.typography.fontFamilyCode,
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    color: 'text.primary',
                  }}
                >
                  {crumb.label}
                </Typography>
              ) : (
                <Button
                  size="small"
                  onClick={() => onNavigate?.(crumb.path)}
                  sx={{
                    minWidth: 0,
                    px: 1,
                    py: 0.25,
                    fontFamily: theme.typography.fontFamilyCode,
                    fontSize: '0.72rem',
                    color: 'text.secondary',
                  }}
                >
                  {crumb.label}
                </Button>
              )}
            </Box>
          );
        })}
      </Box>

      {/* Listing */}
      <TableContainer
        sx={{
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2.5,
          overflow: 'hidden',
        }}
      >
        <Table size="small" aria-label="Remote directory listing">
          <TableHead>
            <TableRow>
              {columns.map((column) => (
                <TableCell
                  key={column.id}
                  align={column.align}
                  sortDirection={orderBy === column.id ? orderDir : false}
                  sx={{ display: column.hideBelow ? { xs: 'none', [column.hideBelow]: 'table-cell' } : undefined }}
                >
                  <TableSortLabel
                    active={orderBy === column.id}
                    direction={orderBy === column.id ? orderDir : 'asc'}
                    onClick={() => requestSort(column.id)}
                  >
                    {column.label}
                  </TableSortLabel>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>

          <TableBody>
            {loading &&
              Array.from({ length: 5 }).map((_, rowIndex) => (
                <TableRow key={`skeleton-${rowIndex}`}>
                  {columns.map((column) => (
                    <TableCell
                      key={column.id}
                      sx={{ display: column.hideBelow ? { xs: 'none', [column.hideBelow]: 'table-cell' } : undefined }}
                    >
                      <Skeleton variant="text" width={column.id === 'name' ? '60%' : '45%'} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!loading &&
              sorted.map((entry, index) => {
                const kind = resolveKind(entry);
                const meta = KIND_META[kind];
                const iconColor = isDark ? lighten(meta.color, 0.3) : meta.color;
                const isSelected = selected === entry.name;

                return (
                  <TableRow
                    key={entry.name}
                    onClick={() => setSelected(entry.name)}
                    onDoubleClick={() => activate(entry)}
                    title={entry.isDir ? 'Double-click to open folder' : 'Double-click to preview'}
                    sx={{
                      cursor: 'pointer',
                      backgroundColor: isSelected ? selectedTint : index % 2 === 1 ? stripe : 'transparent',
                      transition: 'background-color 0.15s ease',
                      '&:hover': { backgroundColor: isSelected ? selectedTint : hoverTint },
                      '& td': { borderColor: 'divider' },
                    }}
                  >
                    <TableCell sx={{ maxWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, minWidth: 0 }}>
                        <Box
                          sx={{
                            display: 'inline-flex',
                            color: iconColor,
                            '& svg': { fontSize: 19 },
                          }}
                        >
                          <meta.Icon />
                        </Box>
                        <Typography
                          noWrap
                          sx={{
                            fontFamily: theme.typography.fontFamilyCode,
                            fontSize: '0.78rem',
                            fontWeight: entry.isDir ? 600 : 400,
                          }}
                        >
                          {entry.name}
                        </Typography>
                      </Box>
                    </TableCell>

                    <TableCell sx={{ display: { xs: 'none', sm: 'table-cell' } }}>
                      <Chip
                        label={meta.label}
                        size="small"
                        sx={{
                          height: 20,
                          fontSize: '0.62rem',
                          fontWeight: 600,
                          color: { xs: 'inherit', sm: iconColor },
                          backgroundColor: alpha(meta.color, isDark ? 0.16 : 0.09),
                          border: `1px solid ${alpha(meta.color, isDark ? 0.38 : 0.24)}`,
                        }}
                      />
                    </TableCell>

                    <TableCell align="right" sx={{ display: { xs: 'none', sm: 'table-cell' } }}>
                      <Typography
                        sx={{
                          fontFamily: theme.typography.fontFamilyCode,
                          fontSize: '0.72rem',
                          color: 'text.secondary',
                        }}
                      >
                        {entry.isDir ? '—' : formatBytes(entry.size)}
                      </Typography>
                    </TableCell>

                    <TableCell align="right" sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                      <Typography sx={{ fontSize: '0.72rem', color: 'text.secondary' }}>
                        {formatDate(entry.modified)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                );
              })}
          </TableBody>
        </Table>

        {/* Empty directory */}
        {!loading && sorted.length === 0 && (
          <Box sx={{ py: 7, px: 2, textAlign: 'center' }}>
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
              <FolderOffRounded />
            </Box>
            <Typography sx={{ fontWeight: 600, mb: 0.5 }}>This folder is empty</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              No files or subfolders at{' '}
              <Box
                component="span"
                sx={{ fontFamily: theme.typography.fontFamilyCode, fontSize: '0.78rem' }}
              >
                {currentPath}
              </Box>
            </Typography>
          </Box>
        )}
      </TableContainer>

      <Typography
        className="mono-label"
        sx={{ mt: 1, color: 'text.disabled', fontSize: '0.52rem', textAlign: 'right' }}
      >
        {loading ? 'Scanning…' : `${sorted.length} ${sorted.length === 1 ? 'entry' : 'entries'}`}
      </Typography>
    </Box>
  );
}
