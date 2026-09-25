import axios from "axios";
import { API_BASE_URL, LOGIN_PATH } from "../config/api";

const api = axios.create({
	baseURL: API_BASE_URL,

	timeout: 60000,
	headers: {
		"Content-Type": "application/json",
	},
});

export const TOKEN_KEY = "token";
export const REFRESH_TOKEN_KEY = "refresh_token";
export const TOKEN_EXPIRES_AT_KEY = "token_expires_at";
export const EMAIL_KEY = "user_email";

let refreshPromise = null;

const clearStoredSession = () => {
	localStorage.removeItem(TOKEN_KEY);
	localStorage.removeItem(REFRESH_TOKEN_KEY);
	localStorage.removeItem(TOKEN_EXPIRES_AT_KEY);
	localStorage.removeItem(EMAIL_KEY);
};

const redirectToLogin = () => {
	if (typeof window === "undefined") return;
	const current = window.location.pathname.replace(/\/+$/, "");
	if (current !== LOGIN_PATH) window.location.assign(LOGIN_PATH);
};

const refreshAccessToken = async () => {
	if (!refreshPromise) {
		const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
		if (!refreshToken) return Promise.reject(new Error("No refresh token"));

		refreshPromise = axios
			.post(
				`${API_BASE_URL}/auth/refresh`,
				{ refresh_token: refreshToken },
				{ timeout: 60000, headers: { "Content-Type": "application/json" } },
			)
			.then(({ data }) => {
				if (!data?.success || !data.token)
					throw new Error(data?.message || "Token refresh failed");
				localStorage.setItem(TOKEN_KEY, data.token);
				if (data.refresh_token)
					localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
				if (data.expires_in) {
					localStorage.setItem(
						TOKEN_EXPIRES_AT_KEY,
						String(Date.now() + Number(data.expires_in) * 1000),
					);
				}
				return data;
			})
			.finally(() => {
				refreshPromise = null;
			});
	}
	return refreshPromise;
};

api.interceptors.request.use(
	(config) => {
		const token = localStorage.getItem(TOKEN_KEY);
		if (token) {
			config.headers.Authorization = `Bearer ${token}`;
		}
		return config;
	},
	(error) => Promise.reject(error),
);

api.interceptors.response.use(
	(response) => response,
	async (error) => {
		const status = error?.response?.status;
		const original = error?.config;
		const url = String(original?.url || "");
		const canRefresh =
			status === 401 &&
			original &&
			!original._authRetry &&
			!url.includes("/auth/login") &&
			!url.includes("/auth/refresh") &&
			!url.includes("/auth/logout") &&
			localStorage.getItem(REFRESH_TOKEN_KEY);

		if (canRefresh) {
			original._authRetry = true;
			try {
				const refreshed = await refreshAccessToken();
				original.headers = {
					...(original.headers || {}),
					Authorization: `Bearer ${refreshed.token}`,
				};
				return api(original);
			} catch {}
		}

		if (status === 401) {
			clearStoredSession();
			redirectToLogin();
		}

		return Promise.reject(error);
	},
);

export default api;
