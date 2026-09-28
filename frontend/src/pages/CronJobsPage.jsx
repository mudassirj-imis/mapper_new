import {
	Add,
	CheckCircle,
	Close,
	ContentCopy,
	Done,
	DeleteOutline,
	ErrorOutline,
	History,
	PlayArrow,
	Refresh,
	Schedule,
	Visibility,
} from "@mui/icons-material";
import {
	Alert,
	Box,
	Button,
	Chip,
	CircularProgress,
	Dialog,
	DialogActions,
	DialogContent,
	DialogTitle,
	Divider,
	IconButton,
	MenuItem,
	Paper,
	Stack,
	Switch,
	Table,
	TableBody,
	TableCell,
	TableContainer,
	TableHead,
	TableRow,
	TextField,
	Tooltip,
	Typography,
} from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSnackbar } from "../context/SnackbarContext";
import { useApiMutation, useApiQuery } from "../hooks/useApi";
import scheduledJobService from "../services/scheduledJobService";
import {
	METHODS,
	formatBody,
	formatBytes,
	formatDate,
	formatDuration,
	formatExactTime,
	formatPreciseTime,
	formatRelative,
	getErrorMessage,
	initialJobForm,
	rowsToHeaders,
	scheduleLabel,
	supportsBody,
} from "../services/scheduledJobConstants";

export default function CronJobsPage() {
	const theme = useTheme();
	const queryClient = useQueryClient();
	const { showSnackbar } = useSnackbar();
	const [form, setForm] = useState(initialJobForm);
	const [historyJobId, setHistoryJobId] = useState("");
	const [selectedRunId, setSelectedRunId] = useState(null);
	const [saving, setSaving] = useState(false);
	const [actionId, setActionId] = useState("");
	const jobsQuery = useApiQuery(["scheduled-jobs"], scheduledJobService.getScheduledJobs, { refetchInterval: 15000 });
	const runsQuery = useApiQuery(
		["scheduled-runs", historyJobId],
		() => historyJobId ? scheduledJobService.getScheduledJobRuns(historyJobId, 100) : scheduledJobService.getScheduledRuns(100),
		{ refetchInterval: 15000 },
	);
	// Bodies and header sets are only fetched once a run is actually opened,
	// so the polling list stays small.
	const runDetailQuery = useApiQuery(
		["scheduled-run", selectedRunId],
		() => selectedRunId ? scheduledJobService.getScheduledRunDetail(selectedRunId) : Promise.resolve(null),
		{ enabled: selectedRunId !== null, refetchInterval: 15000 },
	);
	const jobs = useMemo(() => jobsQuery.data || [], [jobsQuery.data]);
	const runs = runsQuery.data || [];
	const jobNames = useMemo(() => Object.fromEntries(jobs.map((job) => [job.job_id, job.name || job.job_id])), [jobs]);
	const readError = (error) => getErrorMessage(error, "The scheduler request failed.");
	const updateForm = (key, value) => setForm((previous) => ({ ...previous, [key]: value }));
	const updateHeaderRow = (index, key, value) => setForm((previous) => ({
		...previous,
		headers: previous.headers.map((row, position) => (position === index ? { ...row, [key]: value } : row)),
	}));
	const addHeaderRow = () => setForm((previous) => ({ ...previous, headers: [...previous.headers, { name: "", value: "" }] }));
	const removeHeaderRow = (index) => setForm((previous) => ({ ...previous, headers: previous.headers.filter((_, position) => position !== index) }));

	const createMutation = useApiMutation(scheduledJobService.createScheduledJob, {
		onSuccess: async () => {
			setSaving(false);
			setForm(initialJobForm);
			await queryClient.invalidateQueries({ queryKey: ["scheduled-jobs"] });
			showSnackbar("Cron job created", "success");
		},
		onError: (error) => { setSaving(false); showSnackbar(readError(error), "error"); },
	});
	const actionMutation = useApiMutation(
		({ action, job }) => action === "toggle"
			? scheduledJobService.toggleScheduledJob(job.job_id, !job.enabled)
			: action === "run"
				? scheduledJobService.runScheduledJob(job.job_id)
				: scheduledJobService.deleteScheduledJob(job.job_id),
		{
			onSuccess: async (result, variables) => {
				setActionId("");
				await Promise.all([
					queryClient.invalidateQueries({ queryKey: ["scheduled-jobs"] }),
					queryClient.invalidateQueries({ queryKey: ["scheduled-runs"] }),
				]);
				const message = variables.action === "toggle" ? (result.enabled ? "Cron job resumed" : "Cron job paused") : variables.action === "run" ? "Cron job executed" : "Cron job deleted";
				showSnackbar(message, "success");
			},
			onError: (error) => { setActionId(""); showSnackbar(readError(error), "error"); },
		},
	);

	const submit = (event) => {
		event.preventDefault();
		setSaving(true);
		const payload = { url: form.url.trim(), method: form.method, name: form.name.trim() || null };
		if (form.job_id.trim()) payload.job_id = form.job_id.trim();
		payload[form.scheduleType === "interval" ? "interval_seconds" : "cron"] = form.scheduleType === "interval" ? Number.parseInt(form.intervalSeconds, 10) : form.cron.trim();
		const headers = rowsToHeaders(form.headers);
		if (Object.keys(headers).length) payload.headers = headers;
		if (form.body.trim()) payload.body = form.body;
		createMutation.mutate(payload);
	};
	const act = (action, job) => {
		if (action === "delete" && !window.confirm(`Delete “${job.name || job.job_id}”? Past runs will be kept.`)) return;
		setActionId(job.job_id);
		actionMutation.mutate({ action, job });
	};
	const error = jobsQuery.error || runsQuery.error;
	const refreshing = jobsQuery.isFetching || runsQuery.isFetching;

	return (
		<Box>
			<Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2, flexWrap: "wrap", mb: 2.5 }}>
				<Box sx={{ flex: "1 1 360px" }}>
					<Typography className="mono-label" sx={{ color: "primary.main", mb: 0.75 }}>Automation · Recurring HTTP calls</Typography>
					<Typography variant="h5" sx={{ mb: 0.5 }}>Cron Jobs</Typography>
					<Typography variant="body2" sx={{ color: "text.secondary", maxWidth: 700 }}>Create cron or interval-based API calls. Every execution is retained in the dedicated scheduler SQLite database.</Typography>
				</Box>
				<Stack direction="row" spacing={1} alignItems="center">
					<Chip size="small" label={`${jobs.filter((job) => job.enabled).length} active`} icon={<Schedule fontSize="small" />} sx={{ backgroundColor: alpha(theme.palette.primary.main, 0.1) }} />
					<Tooltip title="Refresh" arrow><span><IconButton onClick={() => { jobsQuery.refetch(); runsQuery.refetch(); }} disabled={refreshing} aria-label="Refresh scheduler data"><Refresh /></IconButton></span></Tooltip>
				</Stack>
			</Box>
			<CreateForm form={form} saving={saving} onChange={updateForm} onHeaderChange={updateHeaderRow} onHeaderAdd={addHeaderRow} onHeaderRemove={removeHeaderRow} onSubmit={submit} />
			{error ? <Alert severity="error" sx={{ mb: 2 }}>{readError(error)}</Alert> : null}
			<JobTable jobs={jobs} loading={jobsQuery.isLoading} actionId={actionId} onAction={act} />
			<RunTable runs={runs} loading={runsQuery.isLoading} jobNames={jobNames} historyJobId={historyJobId} onHistoryJobChange={setHistoryJobId} onSelectRun={setSelectedRunId} />
			<RunDetailDialog runId={selectedRunId} query={runDetailQuery} jobNames={jobNames} onClose={() => setSelectedRunId(null)} />
		</Box>
	);
}

function CreateForm({ form, saving, onChange, onHeaderChange, onHeaderAdd, onHeaderRemove, onSubmit }) {
	const bodyAllowed = supportsBody(form.method);
	return <Paper component="form" onSubmit={onSubmit} elevation={0} sx={{ p: { xs: 2, sm: 2.5 }, mb: 2, borderRadius: 3, border: "1px solid", borderColor: "divider" }}>
		<Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}><Add color="primary" /><Typography variant="subtitle1">Create a scheduled request</Typography></Stack>
		<Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "1.4fr .8fr .6fr 1fr" }, gap: 1.5 }}>
			<TextField label="API URL" placeholder="https://api.example.com/health" value={form.url} onChange={(event) => onChange("url", event.target.value)} required fullWidth size="small" />
			<TextField label="Display name" value={form.name} onChange={(event) => onChange("name", event.target.value)} fullWidth size="small" />
			<TextField select label="Method" value={form.method} onChange={(event) => onChange("method", event.target.value)} fullWidth size="small">{METHODS.map((method) => <MenuItem key={method} value={method}>{method}</MenuItem>)}</TextField>
			<TextField label="Job ID (optional)" value={form.job_id} onChange={(event) => onChange("job_id", event.target.value)} fullWidth size="small" />
		</Box>
		<Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "180px 1fr" }, gap: 1.5, mt: 1.5 }}>
			<TextField select label="Schedule type" value={form.scheduleType} onChange={(event) => onChange("scheduleType", event.target.value)} fullWidth size="small"><MenuItem value="interval">Every interval</MenuItem><MenuItem value="cron">Cron expression</MenuItem></TextField>
			{form.scheduleType === "interval" ? <TextField label="Interval in seconds" type="number" inputProps={{ min: 1, step: 1 }} value={form.intervalSeconds} onChange={(event) => onChange("intervalSeconds", event.target.value)} required fullWidth size="small" /> : <TextField label="Cron expression" placeholder="*/5 * * * *" helperText="minute hour day month weekday" value={form.cron} onChange={(event) => onChange("cron", event.target.value)} required fullWidth size="small" />}
		</Box>
		<HeaderEditor rows={form.headers} onChange={onHeaderChange} onAdd={onHeaderAdd} onRemove={onHeaderRemove} />
		{bodyAllowed ? <Box sx={{ mt: 1.5 }}>
			<Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}><Typography variant="subtitle2">Request body</Typography><Typography variant="caption" color="text.secondary">Content-Type is inferred from the body unless you set the header yourself.</Typography></Stack>
			<TextField label="Body" placeholder={'{\n  "example": true\n}'} value={form.body} onChange={(event) => onChange("body", event.target.value)} fullWidth multiline minRows={4} maxRows={14} size="small" className="mono" InputProps={{ sx: { fontFamily: "var(--font-mono)", fontSize: "0.8rem" } }} />
		</Box> : null}
		<Box sx={{ display: "flex", justifyContent: "flex-end", mt: 2 }}><Button type="submit" variant="contained" disabled={saving || !form.url.trim()} startIcon={saving ? <CircularProgress size={15} color="inherit" /> : <Add />}>Create cron job</Button></Box>
	</Paper>;
}

function HeaderEditor({ rows, onChange, onAdd, onRemove }) {
	return <Box sx={{ mt: 1.5 }}>
		<Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
			<Typography variant="subtitle2">Request headers</Typography>
			<Button size="small" onClick={onAdd} startIcon={<Add fontSize="small" />}>Add header</Button>
		</Stack>
		{rows.length === 0 ? <Typography variant="caption" color="text.secondary">No custom headers. Host, Content-Length and connection headers are managed by the scheduler.</Typography> : <Stack spacing={1}>
			{rows.map((row, index) => <Stack key={index} direction="row" spacing={1} alignItems="center">
				<TextField label="Name" value={row.name} onChange={(event) => onChange(index, "name", event.target.value)} placeholder="Authorization" size="small" sx={{ flex: "0 1 260px" }} />
				<TextField label="Value" value={row.value} onChange={(event) => onChange(index, "value", event.target.value)} placeholder="Bearer token" size="small" sx={{ flex: 1 }} />
				<Tooltip title="Remove header"><span><IconButton size="small" onClick={() => onRemove(index)} aria-label={`Remove header ${row.name || index + 1}`}><DeleteOutline fontSize="small" /></IconButton></span></Tooltip>
			</Stack>)}
		</Stack>}
	</Box>;
}

function JobTable({ jobs, loading, actionId, onAction }) {
	return <Paper elevation={0} sx={{ mb: 2, borderRadius: 3, border: "1px solid", borderColor: "divider", overflow: "hidden" }}>
		<Box sx={{ px: 2, py: 1.5, display: "flex", alignItems: "center", gap: 1.25, borderBottom: "1px solid", borderColor: "divider" }}><Schedule sx={{ color: "text.secondary", fontSize: 20 }} /><Typography variant="subtitle2">Scheduled jobs</Typography><Chip size="small" label={jobs.length} /></Box>
		{loading ? <Box sx={{ py: 6, textAlign: "center" }}><CircularProgress size={26} /></Box> : jobs.length === 0 ? <Box sx={{ py: 6, textAlign: "center" }}><Typography variant="body2" color="text.secondary">No cron jobs yet.</Typography></Box> : <TableContainer><Table size="small"><TableHead><TableRow><TableCell>Job</TableCell><TableCell>Schedule</TableCell><TableCell>Next run</TableCell><TableCell>Last result</TableCell><TableCell align="right">Actions</TableCell></TableRow></TableHead><TableBody>{jobs.map((job) => { const busy = actionId === job.job_id; return <TableRow key={job.job_id} hover><TableCell><Typography variant="body2" fontWeight={600}>{job.name || job.job_id}</Typography><Typography variant="caption" color="text.secondary" className="mono">{job.job_id} · {job.method} · {job.url}</Typography></TableCell><TableCell><Typography variant="body2" className="mono">{scheduleLabel(job)}</Typography></TableCell><TableCell><Typography variant="body2">{formatDate(job.next_run_time)}</Typography></TableCell><TableCell>{job.last_run_at ? <Chip size="small" color={job.last_success ? "success" : "error"} label={job.last_success ? "Success" : "Failed"} /> : <Typography variant="body2" color="text.disabled">No runs yet</Typography>}<Typography variant="caption" display="block" color="text.secondary">{formatDate(job.last_run_at)}</Typography></TableCell><TableCell align="right"><Switch size="small" checked={job.enabled} disabled={busy} onChange={() => onAction("toggle", job)} inputProps={{ "aria-label": `Toggle ${job.job_id}` }} /><Tooltip title="Run now"><span><IconButton size="small" disabled={busy} onClick={() => onAction("run", job)} aria-label={`Run ${job.job_id} now`}>{busy ? <CircularProgress size={17} /> : <PlayArrow fontSize="small" />}</IconButton></span></Tooltip><Tooltip title="Delete"><span><IconButton size="small" disabled={busy} onClick={() => onAction("delete", job)} aria-label={`Delete ${job.job_id}`}><DeleteOutline fontSize="small" /></IconButton></span></Tooltip></TableCell></TableRow>; })}</TableBody></Table></TableContainer>}
	</Paper>;
}

function RunTable({ runs, loading, jobNames, historyJobId, onHistoryJobChange, onSelectRun }) {
	return <Paper elevation={0} sx={{ borderRadius: 3, border: "1px solid", borderColor: "divider", overflow: "hidden" }}>
		<Box sx={{ px: 2, py: 1.5, display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap", borderBottom: "1px solid", borderColor: "divider" }}><History sx={{ color: "text.secondary", fontSize: 20 }} /><Typography variant="subtitle2">Past runs</Typography><Chip size="small" label={runs.length} /><TextField select label="Job" value={historyJobId} onChange={(event) => onHistoryJobChange(event.target.value)} size="small" sx={{ ml: "auto", minWidth: 190 }}><MenuItem value="">All jobs</MenuItem>{Object.entries(jobNames).map(([jobId, name]) => <MenuItem key={jobId} value={jobId}>{name}</MenuItem>)}</TextField><Typography className="mono-label" color="text.disabled">SQLite history</Typography></Box>
		{loading ? <Box sx={{ py: 6, textAlign: "center" }}><CircularProgress size={26} /></Box> : runs.length === 0 ? <Box sx={{ py: 6, textAlign: "center" }}><Typography variant="body2" color="text.secondary">No executions have been recorded yet.</Typography></Box> : <TableContainer><Table size="small"><TableHead><TableRow><TableCell>Timestamp</TableCell><TableCell>Job</TableCell><TableCell>Method</TableCell><TableCell align="center">Status</TableCell><TableCell align="right">Duration</TableCell><TableCell>Error</TableCell><TableCell align="right">Detail</TableCell></TableRow></TableHead><TableBody>{runs.map((run) => <TableRow key={run.id} hover onClick={() => onSelectRun(run.id)} sx={{ cursor: "pointer" }}><TableCell><Tooltip title={`${formatPreciseTime(run.ran_at)} · ${formatExactTime(run.ran_at)}`}><span><Typography variant="body2" className="mono" sx={{ whiteSpace: "nowrap" }}>{formatExactTime(run.ran_at)}</Typography><Typography variant="caption" display="block" color="text.secondary">{formatRelative(run.ran_at)}</Typography></span></Tooltip></TableCell><TableCell>{jobNames[run.job_id] || run.job_id}</TableCell><TableCell className="mono">{run.method}</TableCell><TableCell align="center"><Chip size="small" color={run.success ? "success" : "error"} icon={run.success ? <CheckCircle /> : <ErrorOutline />} label={run.status_code || "Error"} /></TableCell><TableCell align="right" className="mono">{formatDuration(run.duration_ms)}</TableCell><TableCell><Typography variant="caption" color={run.error ? "error.main" : "text.disabled"}>{run.error || "—"}</Typography></TableCell><TableCell align="right"><Tooltip title="View request and response detail"><span><IconButton size="small" onClick={(event) => { event.stopPropagation(); onSelectRun(run.id); }} aria-label={`View detail of run ${run.id}`}><Visibility fontSize="small" /></IconButton></span></Tooltip></TableCell></TableRow>)}</TableBody></Table></TableContainer>}
	</Paper>;
}

function HeaderTable({ title, headers, empty }) {
	const entries = Object.entries(headers || {});
	return <Box sx={{ mb: 2 }}>
		<Typography className="mono-label" color="text.secondary" sx={{ mb: 0.75 }}>{title}</Typography>
		{entries.length === 0 ? <Typography variant="body2" color="text.disabled">{empty}</Typography> : <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 2, overflow: "hidden" }}><Table size="small"><TableBody>{entries.map(([name, value]) => <TableRow key={name}><TableCell sx={{ fontFamily: "var(--font-mono)", fontSize: "0.74rem", whiteSpace: "nowrap", verticalAlign: "top", width: 1 }}>{name}</TableCell><TableCell sx={{ fontFamily: "var(--font-mono)", fontSize: "0.74rem", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{value}</TableCell></TableRow>)}</TableBody></Table></Box>}
	</Box>;
}

function RunDetailDialog({ runId, query, jobNames, onClose }) {
	const theme = useTheme();
	const [copied, setCopied] = useState(false);
	const run = query?.data;
	const responseText = useMemo(() => formatBody(run?.response_body), [run?.response_body]);
	const handleCopy = async () => {
		try {
			await navigator.clipboard.writeText(responseText || "");
			setCopied(true);
			window.setTimeout(() => setCopied(false), 1800);
		} catch {
			setCopied(false);
		}
	};
	return <Dialog open={runId !== null} onClose={onClose} maxWidth="md" fullWidth>
		<DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
			<Box sx={{ flex: 1, minWidth: 0 }}>
				<Typography variant="subtitle1">Run detail</Typography>
				{run ? <Typography variant="caption" color="text.secondary" className="mono">{jobNames[run.job_id] || run.job_id} · {run.method} · {formatExactTime(run.ran_at)}</Typography> : null}
			</Box>
			<IconButton onClick={onClose} aria-label="Close run detail"><Close /></IconButton>
		</DialogTitle>
		<Divider />
		<DialogContent dividers>
			{query?.isLoading ? <Box sx={{ py: 5, textAlign: "center" }}><CircularProgress size={26} /></Box> : query?.error ? <Alert severity="error">{getErrorMessage(query.error, "Could not load the run detail.")}</Alert> : !run ? <Typography variant="body2" color="text.secondary">This run is no longer available.</Typography> : <Box>
				<Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2, flexWrap: "wrap" }}>
					<Chip size="small" color={run.success ? "success" : "error"} icon={run.success ? <CheckCircle /> : <ErrorOutline />} label={run.status_code || "Error"} />
					<Typography variant="body2" className="mono">{formatDuration(run.duration_ms)}</Typography>
					<Typography variant="caption" color="text.secondary">{formatBytes(run.response_size)} response</Typography>
					<Tooltip title={`UTC ${formatPreciseTime(run.ran_at)}`}><span><Typography variant="caption" color="text.secondary" className="mono">{formatRelative(run.ran_at)}</Typography></span></Tooltip>
					{run.response_body_truncated ? <Chip size="small" color="warning" label="Body truncated" /> : null}
				</Stack>
				<Typography variant="body2" className="mono" sx={{ mb: 0.5, wordBreak: "break-all" }}>{run.method} {run.url}</Typography>
				{run.error ? <Alert severity={run.success ? "info" : "error"} sx={{ my: 1.5 }}>{run.error}</Alert> : null}
				<Divider sx={{ my: 2 }} />
				<HeaderTable title="Request headers" headers={run.request_headers} empty="No request headers were captured for this run." />
				<HeaderTable title="Response headers" headers={run.response_headers} empty="No response headers were captured for this run." />
				<Box>
					<Stack direction="row" alignItems="center" sx={{ mb: 0.75 }}>
						<Typography className="mono-label" color="text.secondary" sx={{ flex: 1 }}>Response body</Typography>
						<Tooltip title={copied ? "Copied" : "Copy body"} arrow><span><Button size="small" disabled={!responseText} onClick={handleCopy} startIcon={copied ? <Done fontSize="small" /> : <ContentCopy fontSize="small" />}>Copy</Button></span></Tooltip>
					</Stack>
					{responseText ? <Box component="pre" sx={{ m: 0, p: 2, maxHeight: 380, overflow: "auto", border: "1px solid", borderColor: "divider", borderRadius: 2, backgroundColor: alpha(theme.palette.background.default, theme.palette.mode === "dark" ? 0.6 : 0.7), fontFamily: "var(--font-mono)", fontSize: "0.76rem", lineHeight: 1.65, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{responseText}</Box> : <Typography variant="body2" color="text.disabled">This run returned no body.</Typography>}
					{run.response_body_truncated ? <Typography variant="caption" color="warning.main">Only the first {formatBytes(run.response_size)} of the response were stored.</Typography> : null}
				</Box>
			</Box>}
		</DialogContent>
		<DialogActions sx={{ px: 2.5, py: 1.5 }}>
			<Box sx={{ flex: 1 }} />
			<Button size="small" variant="contained" onClick={onClose}>Close</Button>
		</DialogActions>
	</Dialog>;
}


