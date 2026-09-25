import { Box, Chip, Paper, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";

export default function PagePlaceholder({
	icon,
	title,
	description,
	eyebrow = "Module",
	note = "Scheduled for implementation",
}) {
	const theme = useTheme();
	const { primary, secondary } = theme.palette;

	return (
		<Paper
			elevation={0}
			sx={{
				position: "relative",
				overflow: "hidden",
				border: "1px dashed",
				borderColor: "divider",
				borderRadius: 3,
				py: { xs: 7, sm: 10 },
				px: 3,
				textAlign: "center",
				backgroundColor: alpha(theme.palette.background.paper, 0.65),
			}}
		>
			{}
			<Box
				aria-hidden
				sx={{
					position: "absolute",
					width: 340,
					height: 340,
					top: -190,
					right: -140,
					borderRadius: "50%",
					filter: "blur(60px)",
					pointerEvents: "none",
					backgroundColor: alpha(
						primary.main,
						theme.palette.mode === "dark" ? 0.18 : 0.1,
					),
				}}
			/>

			<Box
				sx={{
					width: 62,
					height: 62,
					mx: "auto",
					mb: 3,
					display: "flex",
					alignItems: "center",
					justifyContent: "center",
					borderRadius: 3,
					border: `1px solid ${alpha(primary.main, 0.25)}`,
					backgroundColor: alpha(
						primary.main,
						theme.palette.mode === "dark" ? 0.14 : 0.08,
					),
					color: "primary.main",
					"& svg": { fontSize: 30 },
				}}
			>
				{icon}
			</Box>

			<Typography className="mono-label" sx={{ color: "text.disabled", mb: 1 }}>
				{eyebrow}
			</Typography>

			<Typography variant="h5" sx={{ mb: 1.25 }}>
				{title}
			</Typography>

			<Typography
				variant="body2"
				sx={{ color: "text.secondary", maxWidth: 480, mx: "auto", mb: 3.5 }}
			>
				{description}
			</Typography>

			<Chip
				label={note}
				size="small"
				sx={{
					fontFamily: theme.typography.fontFamilyCode,
					fontSize: "0.66rem",
					letterSpacing: "0.04em",
					color: "text.secondary",
					backgroundColor: alpha(
						secondary.main,
						theme.palette.mode === "dark" ? 0.14 : 0.07,
					),
					border: `1px solid ${alpha(secondary.main, 0.28)}`,
					borderRadius: "7px",
				}}
			/>
		</Paper>
	);
}
