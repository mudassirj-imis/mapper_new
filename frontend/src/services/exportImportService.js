import api from "./api";

export const downloadBlob = (blob, filename = "download") => {
	const url = URL.createObjectURL(blob);
	const link = document.createElement("a");
	link.href = url;
	link.download = filename;
	link.rel = "noopener";
	document.body.appendChild(link);
	link.click();
	link.remove();
	window.setTimeout(() => URL.revokeObjectURL(url), 1500);
};

const fetchExport = async (path) => {
	const response = await api.get(path, { responseType: "blob" });
	return response.data;
};

export const exportJson = () => fetchExport("/export/json");
export const exportCsv = () => fetchExport("/export/csv");
export const exportPostman = () => fetchExport("/export/postman");

const postImport = async (path, file) => {
	const formData = new FormData();
	formData.append("file", file);
	const response = await api.post(path, formData, {
		headers: { "Content-Type": "multipart/form-data" },
	});
	return response.data;
};

export const importJson = (file) => postImport("/import/json", file);
export const importCsv = (file) => postImport("/import/csv", file);
export const importPostman = (file) => postImport("/import/postman", file);

export const IMPORT_HANDLERS = {
	json: importJson,
	csv: importCsv,
	postman: importPostman,
};

export const readApiError = async (error) => {
	const data = error?.response?.data;

	if (data instanceof Blob) {
		try {
			const text = await data.text();
			try {
				const parsed = JSON.parse(text);
				return parsed?.detail || parsed?.message || text || "Request failed";
			} catch {
				return text || "Request failed";
			}
		} catch {
			return "Request failed";
		}
	}

	const detail = data?.detail ?? data?.message;
	if (typeof detail === "string" && detail) return detail;
	if (Array.isArray(detail) && detail.length) {
		return detail.map((item) => item?.msg || String(item)).join("; ");
	}
	return error?.message || "Request failed";
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
