import api from './api';

/**
 * Export / import service — portable mapping bundles.
 *
 * Backend contract (expected):
 *   GET  /api/export/json     -> file blob
 *   GET  /api/export/csv      -> file blob
 *   GET  /api/export/postman  -> file blob (Postman v2.1 collection)
 *   POST /api/import/json     -> { success, imported_endpoints, imported_mappings, errors }
 *   POST /api/import/csv      -> same shape
 *   POST /api/import/postman  -> same shape
 */

/**
 * Trigger a browser download for a blob.
 * Creates a temporary object URL, clicks an anchor and revokes the URL on
 * the next tick (Safari needs the delay before revocation).
 */
export const downloadBlob = (blob, filename = 'download') => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1500);
};

const fetchExport = async (path) => {
  const response = await api.get(path, { responseType: 'blob' });
  return response.data;
};

export const exportJson = () => fetchExport('/export/json');
export const exportCsv = () => fetchExport('/export/csv');
export const exportPostman = () => fetchExport('/export/postman');

const postImport = async (path, file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post(path, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const importJson = (file) => postImport('/import/json', file);
export const importCsv = (file) => postImport('/import/csv', file);
export const importPostman = (file) => postImport('/import/postman', file);

export const IMPORT_HANDLERS = {
  json: importJson,
  csv: importCsv,
  postman: importPostman,
};

/**
 * Resolve a human-readable message from a failed request.
 * Export calls use `responseType: 'blob'`, so an error body arrives as a
 * Blob — read it back as text and try to parse the JSON envelope.
 */
export const readApiError = async (error) => {
  const data = error?.response?.data;

  if (data instanceof Blob) {
    try {
      const text = await data.text();
      try {
        const parsed = JSON.parse(text);
        return parsed?.detail || parsed?.message || text || 'Request failed';
      } catch {
        return text || 'Request failed';
      }
    } catch {
      return 'Request failed';
    }
  }

  const detail = data?.detail ?? data?.message;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item?.msg || String(item)).join('; ');
  }
  return error?.message || 'Request failed';
};

export default {
  exportJson,
  exportCsv,
  exportPostman,
  importJson,
  importCsv,
  importPostman,
  IMPORT_HANDLERS,
  downloadBlob,
  readApiError,
};
