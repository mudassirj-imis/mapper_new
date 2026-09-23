import api from './api';

/**
 * Gateway service — proxies mapped requests to their target systems.
 *
 * Backend contract (expected):
 *   POST /api/map-and-call
 *     { targetUrl, targetMethod, requestData, headers, endpointId }
 */

export const mapAndCall = async (data) => {
  const { targetUrl, targetMethod, requestData, headers, endpointId } = data;
  const response = await api.post('/map-and-call', {
    targetUrl,
    targetMethod,
    requestData,
    headers,
    endpointId,
  }, {
    // The gateway waits up to API_TIMEOUT_SECONDS (60s) for the upstream before
    // answering, so give this call more headroom than the global default.
    timeout: 90000,
  });
  return response.data;
};

export default { mapAndCall };
