import api from './api';

/**
 * Call log service.
 *
 * Backend contract (expected):
 *   GET /api/call-logs?endpoint_id&status&page&per_page&date_from&date_to
 *   GET /api/call-logs/{id}
 */

export const getLogs = async (params = {}) => {
  const {
    endpoint_id,
    status,
    page,
    per_page,
    date_from,
    date_to,
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
      ...rest,
    },
  });
  return response.data;
};

export const getLogDetail = async (id) => {
  const response = await api.get(`/call-logs/${id}`);
  return response.data;
};

export default { getLogs, getLogDetail };
