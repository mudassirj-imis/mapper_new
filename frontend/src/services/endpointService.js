import api from './api';

/**
 * Endpoint / mapping service.
 *
 * Backend contract (expected):
 *   GET    /api/api-endpoints                      -> [endpoint]
 *   GET    /api/api-endpoints/{id}                 -> endpoint
 *   GET    /api/api-endpoints/{id}/parameters      -> [parameter]
 *   PATCH  /api/api-endpoints/{id}                 -> endpoint  (partial update, e.g. { is_active })
 *   POST   /api/mappings/complete                  -> mapping
 *   PUT    /api/mappings/complete/{id}             -> mapping
 *   DELETE /api/api-endpoints/{id}                 -> { success }
 */

export const getEndpoints = async () => {
  const response = await api.get('/api-endpoints');
  return response.data;
};

export const getEndpoint = async (id) => {
  const response = await api.get(`/api-endpoints/${id}`);
  return response.data;
};

export const getParameters = async (endpointId) => {
  const response = await api.get(`/api-endpoints/${endpointId}/parameters`);
  return response.data;
};

export const saveCompleteMapping = async (data) => {
  const response = await api.post('/mappings/complete', data);
  return response.data;
};

export const updateCompleteMapping = async (id, data) => {
  const response = await api.put(`/mappings/complete/${id}`, data);
  return response.data;
};

export const deleteEndpoint = async (id) => {
  const response = await api.delete(`/api-endpoints/${id}`);
  return response.data;
};

/**
 * Partial endpoint update — the registry uses this to flip ``is_active``.
 * Mirrors the backend ``EndpointUpdate`` schema (every field optional).
 */
export const updateEndpoint = async (id, data) => {
  const response = await api.patch(`/api-endpoints/${id}`, data);
  return response.data;
};

export default {
  getEndpoints,
  getEndpoint,
  getParameters,
  saveCompleteMapping,
  updateCompleteMapping,
  deleteEndpoint,
  updateEndpoint,
};
