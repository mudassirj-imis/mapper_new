from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import asyncssh

from backend.core.config import settings
from backend.services import endpoint_service

logger = logging.getLogger(__name__)

__all__ = ["list_file_preview", "list_remote_files", "test_connection"]

_semaphore = asyncio.Semaphore(int(settings.SFTP_MAX_CONCURRENT))

_CREDENTIAL_FIELDS = ("host", "port", "username", "password", "private_key_path")


def _connect_kwargs(creds: dict) -> dict:
    """Build asyncssh.connect kwargs (omit known_hosts rather than pass None)."""
    kwargs = {
        "host": creds["host"],
        "port": int(creds.get("port") or 22),
        "username": creds.get("username"),
        "connect_timeout": float(settings.SFTP_CONNECT_TIMEOUT_SECONDS),
        "login_timeout": float(settings.SFTP_LOGIN_TIMEOUT_SECONDS),
    }
    if creds.get("password"):
        kwargs["password"] = creds["password"]
    if creds.get("private_key_path"):
        kwargs["client_keys"] = [creds["private_key_path"]]
    if settings.SFTP_KNOWN_HOSTS_FILE:
        kwargs["known_hosts"] = settings.SFTP_KNOWN_HOSTS_FILE
    return kwargs


async def _resolved_creds(db, config: dict) -> dict:
    """Start from stored endpoint creds (if any), then overlay overrides."""
    creds: dict = {}
    endpoint_id = config.get("endpoint_id")
    if endpoint_id:
        endpoint = await endpoint_service.get_endpoint(db, endpoint_id)
        if endpoint is None:
            raise FileNotFoundError("Endpoint not found for SFTP operation")
        creds = {
            "host": endpoint.sftp_host,
            "port": endpoint.sftp_port,
            "username": endpoint.sftp_username,
            "password": endpoint.sftp_password,
            "private_key_path": endpoint.sftp_private_key_path,
        }
    for field in _CREDENTIAL_FIELDS:
        value = config.get(field)
        if value not in (None, ""):
            creds[field] = value
    if not creds.get("host"):
        raise ValueError("An SFTP host is required")
    return creds


async def _connect(creds: dict) -> asyncssh.SSHClientConnection:
    async with _semaphore:
        return await asyncssh.connect(**_connect_kwargs(creds))


async def _close(connection) -> None:
    try:
        connection.close()
        await connection.wait_closed()
    except Exception:
        logger.debug("Error closing SFTP connection", exc_info=True)


def _join(path: str, name: str) -> str:
    base = (path or "/").rstrip("/") or "/"
    return f"{base}/{name}" if base != "/" else f"/{name}"


def _entry(name: str, stat) -> dict:
    modified = None
    mtime = getattr(stat, "mtime", 0) or 0
    if mtime:
        modified = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
    return {
        "name": name,
        "is_dir": bool(getattr(stat, "is_dir", lambda: False)()),
        "size": int(getattr(stat, "size", 0) or 0),
        "modified": modified,
    }


async def test_connection(db, config: dict) -> dict:
    """Attempt a connection and return ``{success, message}``."""
    creds = await _resolved_creds(db, config)
    connection = await _connect(creds)
    await _close(connection)
    return {
        "success": True,
        "message": f"Connected to {creds['host']} (port {creds.get('port') or 22})",
    }


async def list_remote_files(db, config: dict) -> dict:
    """Return ``{path, files: [{name, is_dir, size, modified}]}``."""
    creds = await _resolved_creds(db, config)
    remote_path = config.get("remote_path") or "/"
    connection = await _connect(creds)
    try:
        sftp = await connection.start_sftp_client()
        try:
            names = await sftp.listdir(remote_path)
            files = []
            for name in names[: int(settings.SFTP_MAX_ENTRIES)]:
                full = _join(remote_path, name)
                try:
                    stat = await sftp.stat(full)
                except Exception:
                    stat = None
                files.append(_entry(name, stat))
            return {"path": remote_path, "files": files}
        finally:
            try:
                sftp.close()
            except Exception:
                pass
    finally:
        await _close(connection)


async def list_file_preview(db, config: dict) -> dict:
    """Read up to the configured byte cap of a remote file for previewing."""
    creds = await _resolved_creds(db, config)
    remote_path = config.get("remote_path") or "/"
    filename = config.get("filename") or ""
    full = _join(remote_path, filename)
    connection = await _connect(creds)
    try:
        sftp = await connection.start_sftp_client()
        try:
            total_size = None
            try:
                total_size = int((await sftp.stat(full)).size or 0)
            except Exception:
                pass
            async with sftp.open(full, "rb") as handle:
                data = await handle.read(int(settings.SFTP_PREVIEW_MAX_BYTES))
            content = data.decode("utf-8", errors="replace")
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            file_type = "csv" if ext == "csv" else "json"
            return {
                "filename": filename,
                "file_type": file_type,
                "content": content,
                "size": total_size if total_size is not None else len(data),
            }
        finally:
            try:
                sftp.close()
            except Exception:
                pass
    finally:
        await _close(connection)
