import api from "./api";

const compact = (payload) =>
	Object.fromEntries(
		Object.entries(payload).filter(
			([, value]) => value !== undefined && value !== null && value !== "",
		),
	);

const connectionFields = (config = {}) =>
	compact({
		host: config.host,
		port: config.port,
		username: config.username,
		password: config.password,
		endpoint_id: config.endpoint_id ?? config.endpointId,
	});

export const testConnection = async (config = {}) => {
	const response = await api.post(
		"/sftp/test-connection",
		connectionFields(config),
	);
	return response.data;
};

export const listFiles = async (config = {}) => {
	const response = await api.post("/sftp/list-files", {
		...connectionFields(config),
		remote_path: config.remote_path || config.remotePath || "/",
	});
	return response.data;
};

export const previewFile = async (config = {}) => {
	const response = await api.post("/sftp/preview", {
		...connectionFields(config),
		remote_path: config.remote_path || config.remotePath || "/",
		filename: config.filename,
	});
	return response.data;
};

export default { testConnection, listFiles, previewFile };
