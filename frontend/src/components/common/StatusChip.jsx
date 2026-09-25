import { Chip } from "@mui/material";
import { alpha, lighten, useTheme } from "@mui/material/styles";

export const STATUS_COLORS = {
	success: "#2e7d32",
	failed: "#d32f2f",
	pending: "#e8a200",
};

const STATUS_LABELS = {
	success: "Success",
	failed: "Failed",
	pending: "Pending",
};

const STATUS_ALIASES = {
	ok: "success",
	completed: "success",
	error: "failed",
	failure: "failed",
	running: "pending",
	in_progress: "pending",
	queued: "pending",
};

function normalizeStatus(status) {
	const raw = String(status || "")
		.trim()
		.toLowerCase()
		.replace(/[\s-]/g, "_");
	return STATUS_ALIASES[raw] || raw;
}

export default function StatusChip({
	status = "pending",
	size = "small",
	sx,
	...rest
}) {
	const theme = useTheme();
	const isDark = theme.palette.mode === "dark";

	const key = normalizeStatus(status);
	const known = Boolean(STATUS_COLORS[key]);
	const base = STATUS_COLORS[key] || (isDark ? "#93a4bd" : "#5c6b81");
	const textColor = isDark ? lighten(base, 0.42) : base;
	const label =
		STATUS_LABELS[key] ||
		(key ? key.charAt(0).toUpperCase() + key.slice(1) : "Unknown");

	return (
		<Chip
			size={size}
			label={
				<span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
					<span
						aria-hidden
						style={{
							width: 6,
							height: 6,
							borderRadius: "50%",
							backgroundColor: "currentColor",
							boxShadow: known
								? `0 0 0 3px ${alpha(base, isDark ? 0.25 : 0.15)}`
								: "none",
						}}
					/>
					{label}
				</span>
			}
			sx={{
				fontSize: "0.72rem",
				fontWeight: 600,
				height: 24,
				borderRadius: "7px",
				color: textColor,
				backgroundColor: alpha(base, isDark ? 0.16 : 0.09),
				border: `1px solid ${alpha(base, isDark ? 0.4 : 0.26)}`,
				"& .MuiChip-label": { px: 1.1 },
				...sx,
			}}
			{...rest}
		/>
	);
}
