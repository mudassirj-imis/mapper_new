import api from './api';

/**
 * SFTP service — talks to the backend bridge that speaks to remote servers.
 *
 * Backend contract (expected):
 *   POST /api/sftp/test-connection
 *     { host, port, username, password, endpoint_id } -> { success, message }
 *   POST /api/sftp/list-files
 *     { host, port, username, password, endpoint_id, remote_path }
 *     -> { path, files: [{ name, is_dir, size, modified }] }
 *   POST /api/sftp/preview
 *     { host, port, username, password, endpoint_id, remote_path, filename }
 *     -> { filename, file_type, content, size }
 *
 * When `endpoint_id` is present the backend resolves the stored (encrypted)
 * credentials for that endpoint and any field sent here acts as an override.
 */

/** Drop empty values so the backend can fall back to stored credentials. */
const compact = (payload) =>
  Object.fromEntries(
    Object.entries(payload).filter(
      ([, value]) => value !== undefined && value !== null && value !== ''
    )
  );

/** Shared connection fragment for every SFTP call. */
const connectionFields = (config = {}) =>
  compact({
    host: config.host,
    port: config.port,
    username: config.username,
    password: config.password,
    endpoint_id: config.endpoint_id ?? config.endpointId,
  });

export const testConnection = async (config = {}) => {
  const response = await api.post('/sftp/test-connection', connectionFields(config));
  return response.data;
};

export const listFiles = async (config = {}) => {
  const response = await api.post('/sftp/list-files', {
    ...connectionFields(config),
    remote_path: config.remote_path || config.remotePath || '/',
  });
  return response.data;
};

export const previewFile = async (config = {}) => {
  const response = await api.post('/sftp/preview', {
    ...connectionFields(config),
    remote_path: config.remote_path || config.remotePath || '/',
    filename: config.filename,
  });
  return response.data;
};

export default { testConnection, listFiles, previewFile };
