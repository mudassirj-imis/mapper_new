import api from './api';

/**
 * Call log service.
 *
 * Backend contract (expected):
 *   GET /api/call-logs?endpoint_id&status&page&per_page&date_from&date_to&limit
 *   GET /api/call-logs/{id}
 *
 * `limit` is a window over the newest N matches that composes with paging:
 * the result is at most `ceil(limit / per_page)` pages.
 */

export const getLogs = async (params = {}) => {
  const {
    endpoint_id,
    status,
    page,
    per_page,
    date_from,
    date_to,
    limit,
    ...rest
  } = params;

  const response = await api.get('/call-logs', {
    params: {
      ...(endpoint_id !== undefined && endpoint_id !== null && endpoint_id !== ''
        ? { endpoint_id }
        : {}),
      ...(status ? { status } : {}),
      ...(page ? { page } : {}),
      ...(per_page ? { per_page } : {}),
      ...(date_from ? { date_from } : {}),
      ...(date_to ? { date_to } : {}),
      ...(limit ? { limit } : {}),
      ...rest,
    },
  });
  return response.data;
};

/**
 * Fetch up to `limit` newest matching logs for export.
 *
 * `limit` is a window of `ceil(limit / per_page)` pages and `per_page` is
 * capped at 200 server-side, so this walks the window page by page and
 * concatenates the slices.
 */
export const EXPORT_PAGE_SIZE = 200;

export const getLogsForExport = async (params = {}, limit = 1000) => {
  const filters = { ...(params || {}) };
  // Paging is re-derived below; the caller's values do not apply here.
  delete filters.page;
  delete filters.per_page;
  const size = Math.min(EXPORT_PAGE_SIZE, Math.max(1, limit));
  const pageCount = Math.ceil(limit / size);
  const collected = [];
  let total = 0;

  for (let index = 1; index <= pageCount; index += 1) {
    // Sequential on purpose: these are large payloads, and fanning them out
    // would just queue behind the same connection pool.
    const response = await getLogs({ ...filters, page: index, per_page: size, limit });
    const items = response?.items ?? [];
    collected.push(...items);
    total = response?.total ?? total;
    if (items.length < size) break;
  }

  return { items: collected, total, page: 1, per_page: size, pages: pageCount };
};

export const getLogDetail = async (id) => {
  const response = await api.get(`/call-logs/${id}`);
  return response.data;
};

export default { getLogs, getLogsForExport, getLogDetail, EXPORT_PAGE_SIZE };
