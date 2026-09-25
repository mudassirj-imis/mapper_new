import { Box, CircularProgress, Typography } from "@mui/material";
import {
	createContext,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useState,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import {
	EMAIL_KEY,
	REFRESH_TOKEN_KEY,
	TOKEN_EXPIRES_AT_KEY,
	TOKEN_KEY,
} from "../services/api";
import authService from "../services/authService";

const AuthContext = createContext(null);

function SessionLoader() {
	return (
		<Box
			sx={{
				minHeight: "100vh",
				display: "flex",
				flexDirection: "column",
				alignItems: "center",
				justifyContent: "center",
				gap: 2,
				bgcolor: "background.default",
			}}
		>
			<CircularProgress size={30} thickness={4.5} />
			<Typography className="mono-label" sx={{ color: "text.secondary" }}>
				Authenticating
			</Typography>
		</Box>
	);
}

export function AuthProvider({ children }) {
	const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
	const [user, setUser] = useState(() => localStorage.getItem(EMAIL_KEY));
	const [isAuthenticated, setIsAuthenticated] = useState(false);
	const [loading, setLoading] = useState(true);

	const applySession = useCallback(
		(nextToken, nextEmail, nextRefreshToken, expiresIn) => {
			const refreshToken =
				nextRefreshToken === undefined
					? localStorage.getItem(REFRESH_TOKEN_KEY)
					: nextRefreshToken;
			const expiry =
				expiresIn === undefined
					? localStorage.getItem(TOKEN_EXPIRES_AT_KEY)
					: expiresIn;

			if (nextToken) localStorage.setItem(TOKEN_KEY, nextToken);
			else localStorage.removeItem(TOKEN_KEY);
			if (nextEmail) localStorage.setItem(EMAIL_KEY, nextEmail);
			else localStorage.removeItem(EMAIL_KEY);
			if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
			else localStorage.removeItem(REFRESH_TOKEN_KEY);
			if (expiry) localStorage.setItem(TOKEN_EXPIRES_AT_KEY, expiry);
			else localStorage.removeItem(TOKEN_EXPIRES_AT_KEY);

			setToken(nextToken || null);
			setUser(nextEmail || null);
			setIsAuthenticated(Boolean(nextToken));
		},
		[],
	);

	const clearSession = useCallback(() => {
		localStorage.removeItem(TOKEN_KEY);
		localStorage.removeItem(REFRESH_TOKEN_KEY);
		localStorage.removeItem(TOKEN_EXPIRES_AT_KEY);
		localStorage.removeItem(EMAIL_KEY);
		setToken(null);
		setUser(null);
		setIsAuthenticated(false);
	}, []);

	useEffect(() => {
		let cancelled = false;

		const restoreSession = async () => {
			const currentToken = localStorage.getItem(TOKEN_KEY);
			if (currentToken) {
				setIsAuthenticated(true);
				setLoading(false);
				return;
			}

			const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
			if (!storedRefreshToken) {
				setLoading(false);
				return;
			}

			try {
				const refreshed = await authService.refresh(storedRefreshToken);
				if (cancelled) return;

				if (refreshed?.success && refreshed.token) {
					applySession(
						refreshed.token,
						localStorage.getItem(EMAIL_KEY),
						refreshed.refresh_token ?? storedRefreshToken,
						refreshed.expires_in
							? String(Date.now() + Number(refreshed.expires_in) * 1000)
							: undefined,
					);
				} else {
					clearSession();
				}
			} catch {
				if (!cancelled) clearSession();
			} finally {
				if (!cancelled) setLoading(false);
			}
		};

		restoreSession();
		return () => {
			cancelled = true;
		};
	}, [applySession, clearSession]);

	const login = useCallback(
		async (email, password) => {
			const data = await authService.login(email, password);
			if (!data?.success || !data.token) {
				throw new Error(
					data?.detail || data?.message || "Invalid email or password",
				);
			}
			applySession(
				data.token,
				data.email || data.user?.email || email,
				data.refresh_token ?? null,
				data.expires_in
					? String(Date.now() + Number(data.expires_in) * 1000)
					: null,
			);
			return data;
		},
		[applySession],
	);

	const logout = useCallback(async () => {
		try {
			await authService.logout();
		} catch {}
		clearSession();
	}, [clearSession]);

	const value = useMemo(
		() => ({
			user,
			token,
			isAuthenticated,
			loading,
			login,
			logout,
		}),
		[user, token, isAuthenticated, loading, login, logout],
	);

	return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
	const context = useContext(AuthContext);
	if (!context) throw new Error("useAuth must be used within an AuthProvider");
	return context;
}

export function AuthGuard({ children }) {
	const { isAuthenticated, loading } = useAuth();
	const location = useLocation();

	if (loading) return <SessionLoader />;
	if (!isAuthenticated) {
		return <Navigate to="/login" replace state={{ from: location.pathname }} />;
	}
	return children;
}

export default AuthContext;
