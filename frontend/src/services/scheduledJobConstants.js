const toDate = (value) => {
	if (!value) return null;
	const date = value instanceof Date ? value : new Date(value);
	return Number.isNaN(date.getTime()) ? null : date;
};

export const formatDate = (value) => {
	const date = toDate(value);
	if (!date) return value ? String(value) : "—";
	return date.toLocaleString([], {
		year: "numeric",
		month: "short",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	});
};

/**
 * Full timestamp down to the second, for run history where the exact
 * execution time is the point.
 */
export const formatExactTime = (value) => {
	const date = toDate(value);
	if (!date) return value ? String(value) : "—";
	return date.toLocaleString([], {
		year: "numeric",
		month: "short",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
		hour12: false,
	});
};

/** Millisecond precision plus an explicit UTC marker, for the detail view. */
export const formatPreciseTime = (value) => {
	const date = toDate(value);
	if (!date) return value ? String(value) : "—";
	const iso = date.toISOString();
	return `${iso.slice(0, 10)} ${iso.slice(11, 19)}.${iso.slice(20, 23)} UTC`;
};

/** Coarse "how long ago" label, e.g. "just now", "12m ago", "3d ago". */
export const formatRelative = (value) => {
	const date = toDate(value);
	if (!date) return "—";
	const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
	if (seconds < 45) return "just now";
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	if (days < 30) return `${days}d ago`;
	return date.toLocaleDateString();
};

export const formatDuration = (value) => {
	if (value === null || value === undefined) return "—";
	if (value < 1000) return `${value} ms`;
	return `${(value / 1000).toFixed(2)} s`;
};

export const scheduleLabel = (job) => {
	if (!job) return "—";
	if (job.cron) return `Cron · ${job.cron}`;
	if (job.interval_seconds) return `Every ${formatDuration(job.interval_seconds * 1000)}`;
	return "—";
};

export const getErrorMessage = (error, fallback = "Something went wrong.") => {
	const detail = error?.response?.data?.detail;
	if (Array.isArray(detail)) {
		return detail.map((item) => item?.msg || JSON.stringify(item)).join("; ") || fallback;
	}
	if (typeof detail === "string") return detail;
	if (detail) return JSON.stringify(detail);
	return error?.message || fallback;
};

export const METHODS = [
	"GET",
	"POST",
	"PUT",
	"PATCH",
	"DELETE",
	"HEAD",
	"OPTIONS",
];

/** Methods the backend accepts a body for. */
export const METHODS_WITH_BODY = ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"];

export const supportsBody = (method) => METHODS_WITH_BODY.includes(method);

export const formatBytes = (value) => {
	if (value === null || value === undefined) return "—";
	if (value < 1024) return `${value} B`;
	if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
	return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

/** Turn `{ "A": "b" }` into the `[{ name, value }]` rows the form edits. */
export const headersToRows = (headers) =>
	Object.entries(headers || {}).map(([name, value]) => ({ name, value }));

/** Turn form rows back into an object, dropping blank names. */
export const rowsToHeaders = (rows) => {
	const headers = {};
	(rows || []).forEach((row) => {
		const name = (row.name || "").trim();
		if (name) headers[name] = (row.value || "").trim();
	});
	return headers;
};

/** Pretty-print a body when it parses as JSON, otherwise show it verbatim. */
export const formatBody = (body) => {
	if (body === null || body === undefined || body === "") return "";
	try {
		return JSON.stringify(JSON.parse(body), null, 2);
	} catch {
		return body;
	}
};

export const initialJobForm = {
	job_id: "",
	name: "",
	url: "",
	method: "GET",
	scheduleType: "interval",
	intervalSeconds: "60",
	cron: "*/5 * * * *",
	headers: [],
	body: "",
};
