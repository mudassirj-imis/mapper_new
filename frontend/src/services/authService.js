import api, { REFRESH_TOKEN_KEY } from "./api";

export const login = async (email, password) => {
	try {
		const response = await api.post("/auth/login", { email, password });
		return response.data;
	} catch (error) {
		throw new Error(
			error?.response?.data?.message ||
				error?.response?.data?.detail ||
				error?.message ||
				"Invalid email or password",
			{ cause: error },
		);
	}
};

export const validateToken = async () => {
	const response = await api.post("/auth/validate");
	return response.data;
};

export const refresh = async (
	refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY),
) => {
	try {
		const response = await api.post("/auth/refresh", {
			refresh_token: refreshToken,
		});
		return response.data;
	} catch (error) {
		throw new Error(
			error?.response?.data?.message ||
				error?.response?.data?.detail ||
				error?.message ||
				"Token refresh failed",
			{ cause: error },
		);
	}
};

export const logout = async () => {
	const response = await api.post("/auth/logout");
	return response.data;
};

export default { login, refresh, validateToken, logout };
