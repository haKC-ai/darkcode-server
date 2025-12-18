"""Daemon mode for DarkCode Server - runs in background with logging."""

import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from darkcode_server.config import ServerConfig
from darkcode_server.server import DarkCodeServer, ServerState


class DarkCodeDaemon:
    """Daemon wrapper for DarkCode server with logging and notifications."""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig.load()
        self.server: Optional[DarkCodeServer] = None
        self.logger = self._setup_logging()
        self._notification_handlers: list[Callable] = []

        # PID file for process management
        self.pid_file = self.config.config_dir / "darkcode.pid"

    def _setup_logging(self) -> logging.Logger:
        """Set up logging to file and console."""
        self.config.log_dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("darkcode")
        logger.setLevel(logging.INFO)

        # File handler - detailed logs
        log_file = self.config.log_dir / "server.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)

        # Connection log - security events only
        conn_log = self.config.log_dir / "connections.log"
        conn_handler = logging.FileHandler(conn_log)
        conn_handler.setLevel(logging.INFO)
        conn_handler.addFilter(lambda r: "CONNECTION" in r.getMessage() or "AUTH" in r.getMessage())
        conn_handler.setFormatter(file_format)

        logger.addHandler(file_handler)
        logger.addHandler(conn_handler)

        return logger

    def add_notification_handler(self, handler: Callable[[str, str, dict], None]):
        """Add a notification handler. Called with (event_type, message, data)."""
        self._notification_handlers.append(handler)

    def _notify(self, event_type: str, message: str, data: dict = None):
        """Send notification to all handlers."""
        data = data or {}
        for handler in self._notification_handlers:
            try:
                handler(event_type, message, data)
            except Exception as e:
                self.logger.error(f"Notification handler error: {e}")

    def _write_pid(self):
        """Write PID file."""
        self.pid_file.write_text(str(os.getpid()))

    def _remove_pid(self):
        """Remove PID file."""
        self.pid_file.unlink(missing_ok=True)

    @classmethod
    def get_running_pid(cls, config: Optional[ServerConfig] = None) -> Optional[int]:
        """Get PID of running daemon, or None if not running."""
        config = config or ServerConfig.load()
        pid_file = config.config_dir / "darkcode.pid"

        if not pid_file.exists():
            return None

        try:
            pid = int(pid_file.read_text().strip())
            # Check if process is actually running
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            # PID file exists but process isn't running - stale
            pid_file.unlink(missing_ok=True)
            return None

    @classmethod
    def stop_running(cls, config: Optional[ServerConfig] = None) -> bool:
        """Stop running daemon. Returns True if stopped."""
        pid = cls.get_running_pid(config)
        if pid is None:
            return False

        try:
            os.kill(pid, signal.SIGTERM)
            # Wait a bit for graceful shutdown
            import time
            for _ in range(30):  # 3 seconds max
                time.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return True
            # Force kill if still running
            os.kill(pid, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return True
        except PermissionError:
            return False

    def _sanitize_log(self, s: str) -> str:
        """Sanitize string for safe logging.

        SECURITY: Prevents log injection attacks by removing control characters.
        """
        if not s:
            return ""
        # Remove control characters, newlines, and limit length
        return "".join(c for c in s[:256] if c.isprintable() and c not in "\n\r")

    def log_connection(self, client_ip: str, device_id: str, success: bool, reason: str = ""):
        """Log a connection attempt."""
        # Sanitize all inputs to prevent log injection
        client_ip = self._sanitize_log(client_ip)
        device_id = self._sanitize_log(device_id)
        reason = self._sanitize_log(reason)

        status = "SUCCESS" if success else "FAILED"
        msg = f"CONNECTION {status} | IP: {client_ip} | Device: {device_id[:8]}..."
        if reason:
            msg += f" | Reason: {reason}"

        if success:
            self.logger.info(msg)
            self._notify("connection", f"Device connected from {client_ip}", {
                "client_ip": client_ip,
                "device_id": device_id,
            })
        else:
            self.logger.warning(msg)
            self._notify("connection_failed", f"Connection rejected: {reason}", {
                "client_ip": client_ip,
                "device_id": device_id,
                "reason": reason,
            })

    def log_auth_attempt(self, client_ip: str, success: bool, reason: str = ""):
        """Log an authentication attempt."""
        client_ip = self._sanitize_log(client_ip)
        reason = self._sanitize_log(reason)

        status = "SUCCESS" if success else "FAILED"
        msg = f"AUTH {status} | IP: {client_ip}"
        if reason:
            msg += f" | Reason: {reason}"

        if success:
            self.logger.info(msg)
        else:
            self.logger.warning(msg)
            self._notify("auth_failed", f"Auth failed from {client_ip}: {reason}", {
                "client_ip": client_ip,
                "reason": reason,
            })

    def log_device_bound(self, device_id: str, client_ip: str):
        """Log device binding event."""
        msg = f"DEVICE BOUND | Device: {device_id[:8]}... | IP: {client_ip}"
        self.logger.info(msg)
        self._notify("device_bound", f"Server now locked to device from {client_ip}", {
            "device_id": device_id,
            "client_ip": client_ip,
        })

    def log_state_change(self, old_state: ServerState, new_state: ServerState):
        """Log server state change."""
        msg = f"STATE CHANGE | {old_state.value} -> {new_state.value}"
        self.logger.info(msg)
        self._notify("state_change", f"Server is now {new_state.value}", {
            "old_state": old_state.value,
            "new_state": new_state.value,
        })

    async def run(self):
        """Run the daemon."""
        # Check if already running
        existing_pid = self.get_running_pid(self.config)
        if existing_pid:
            self.logger.error(f"Daemon already running with PID {existing_pid}")
            raise RuntimeError(f"Daemon already running with PID {existing_pid}")

        self._write_pid()
        self.logger.info(f"DarkCode daemon starting (PID: {os.getpid()})")
        self.logger.info(f"Listening on {self.config.bind_host}:{self.config.port}")
        self.logger.info(f"Device lock: {'enabled' if self.config.device_lock else 'disabled'}")
        self.logger.info(f"Idle timeout: {self.config.idle_timeout}s")

        self._notify("server_start", f"DarkCode server started on port {self.config.port}", {
            "port": self.config.port,
            "device_lock": self.config.device_lock,
        })

        try:
            self.server = DarkCodeServer(self.config)
            await self.server.start()

            # Set up signal handlers
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self._shutdown()))

            # Run forever
            await asyncio.Future()

        except Exception as e:
            self.logger.error(f"Server error: {e}")
            raise
        finally:
            self._remove_pid()
            self.logger.info("DarkCode daemon stopped")
            self._notify("server_stop", "DarkCode server stopped", {})

    async def _shutdown(self):
        """Graceful shutdown."""
        self.logger.info("Shutdown signal received")
        if self.server:
            await self.server.stop()
        # Stop the event loop
        asyncio.get_event_loop().stop()


def daemonize():
    """Fork into background (Unix only)."""
    if os.name != "posix":
        raise RuntimeError("Daemonize only works on Unix systems")

    # First fork
    pid = os.fork()
    if pid > 0:
        # Parent exits
        sys.exit(0)

    # Decouple from parent
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Second fork
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    with open("/dev/null", "rb", 0) as f:
        os.dup2(f.fileno(), sys.stdin.fileno())

    # Keep stdout/stderr for logging initially
    # They'll be redirected to log files by the logger


def run_daemon(config: Optional[ServerConfig] = None, background: bool = False):
    """Run the daemon, optionally in background."""
    if background and os.name == "posix":
        daemonize()

    daemon = DarkCodeDaemon(config)
    asyncio.run(daemon.run())
