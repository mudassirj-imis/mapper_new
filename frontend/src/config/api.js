export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export const APP_BASE_PATH = (import.meta.env.BASE_URL || "/").replace(
	/\/+$/,
	"",
);

export const LOGIN_PATH = `${APP_BASE_PATH}/login`;

export default API_BASE_URL;
