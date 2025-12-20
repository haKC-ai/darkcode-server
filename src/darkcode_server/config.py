"""Configuration management for DarkCode Server."""

import os
import secrets
import socket
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(24)


def get_hostname() -> str:
    """Get the machine hostname."""
    return socket.gethostname()


def get_default_working_dir() -> Path:
    """Get the default working directory (~/darkcode).

    Creates the directory if it doesn't exist.
    """
    darkcode_dir = Path.home() / "darkcode"
    darkcode_dir.mkdir(parents=True, exist_ok=True)
    return darkcode_dir


class ServerConfig(BaseSettings):
    """Server configuration with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="DARKCODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    port: int = Field(default=3100, description="WebSocket server port")
    host: str = Field(default="0.0.0.0", description="Bind address (use 127.0.0.1 for local only)")
    token: str = Field(default_factory=get_default_token, description="Auth token")
    working_dir: Path = Field(default_factory=get_default_working_dir, description="Working directory for Claude (default: ~/darkcode)")
    browse_dir: Optional[Path] = Field(default=None, description="Default directory for app file browser (defaults to working_dir)")
    server_name: str = Field(default_factory=get_hostname, description="Server display name")

    # Security settings
    max_sessions_per_ip: int = Field(default=3, description="Max concurrent sessions per IP")
    rate_limit_attempts: int = Field(default=5, description="Auth attempts before lockout")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")
    local_only: bool = Field(default=False, description="Only allow connections from localhost")

    # Device binding - lock to first authenticated device
    device_lock: bool = Field(default=True, description="Lock server to first authenticated device")
    idle_timeout: int = Field(default=300, description="Seconds of idle before sleep mode (0=disabled)")
    bound_device_id: Optional[str] = Field(default=None, description="Bound device fingerprint")

    # TLS settings (TLS is mandatory for security)
    tls_enabled: bool = Field(default=True, description="Enable TLS (wss://) - required for security")
    mtls_enabled: bool = Field(default=False, description="Require client certificates (mTLS)")
    tls_cert_path: Optional[Path] = Field(default=None, description="Custom TLS certificate path")
    tls_key_path: Optional[Path] = Field(default=None, description="Custom TLS key path")

    # Token rotation
    token_rotation_days: int = Field(default=30, description="Days before token auto-rotation (0=disabled)")
    token_grace_hours: int = Field(default=24, description="Hours old tokens remain valid after rotation")

    # Claude permission settings
    permission_mode: str = Field(
        default="acceptEdits",
        description="Claude permission mode: default, acceptEdits, or bypassPermissions"
    )

    # Web admin settings
    web_admin_disabled: bool = Field(default=False, description="Disable web admin dashboard")

    @property
    def bind_host(self) -> str:
        """Get the actual bind address based on security settings."""
        if self.local_only:
            return "127.0.0.1"
        return self.host

    @property
    def is_exposed(self) -> bool:
        """Check if server is exposed to network (not localhost-only)."""
        return self.host == "0.0.0.0" and not self.local_only

    @property
    def effective_browse_dir(self) -> Path:
        """Get the effective browse directory for the file browser.

        Returns browse_dir if set, otherwise falls back to working_dir.
        """
        if self.browse_dir is not None:
            return self.browse_dir.resolve()
        return self.working_dir.resolve()

    @property
    def safe_working_dir(self) -> Path:
        """Get validated working directory.

        SECURITY: Resolves to absolute path and validates it exists.
        Prevents path traversal attacks.
        """
        resolved = self.working_dir.resolve()

        # Must exist and be a directory
        if not resolved.exists():
            raise ValueError(f"Working directory does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Working directory is not a directory: {resolved}")

        # Block sensitive system directories
        blocked = ["/", "/etc", "/var", "/usr", "/bin", "/sbin", "/root"]
        if str(resolved) in blocked:
            raise ValueError(f"Cannot use system directory as working dir: {resolved}")

        return resolved

    # Health check settings - very lenient for mobile apps that may be backgrounded
    ping_interval: int = Field(default=900, description="Ping interval in seconds (15 min)")
    ping_timeout: int = Field(default=300, description="Ping timeout in seconds (5 min)")

    # Paths - all config stored in ~/darkcode/.darkcode
    config_dir: Path = Field(
        default_factory=lambda: Path.home() / "darkcode" / ".darkcode",
        description="Config directory (~/darkcode/.darkcode)",
    )
    log_dir: Path = Field(
        default_factory=lambda: Path.home() / "darkcode" / ".darkcode" / "logs",
        description="Log directory",
    )
    sessions_dir: Path = Field(
        default_factory=lambda: Path.home() / "darkcode" / ".darkcode" / "sessions",
        description="Sessions directory",
    )

    def save(self) -> None:
        """Save configuration to file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        env_file = self.config_dir / ".env"

        lines = [
            f"DARKCODE_PORT={self.port}",
            f"DARKCODE_TOKEN={self.token}",
            f"DARKCODE_WORKING_DIR={self.working_dir}",
            f"DARKCODE_SERVER_NAME={self.server_name}",
            f"DARKCODE_MAX_SESSIONS_PER_IP={self.max_sessions_per_ip}",
            f"DARKCODE_LOCAL_ONLY={str(self.local_only).lower()}",
            f"DARKCODE_DEVICE_LOCK={str(self.device_lock).lower()}",
            f"DARKCODE_IDLE_TIMEOUT={self.idle_timeout}",
            f"DARKCODE_TLS_ENABLED={str(self.tls_enabled).lower()}",
            f"DARKCODE_MTLS_ENABLED={str(self.mtls_enabled).lower()}",
            f"DARKCODE_TOKEN_ROTATION_DAYS={self.token_rotation_days}",
            f"DARKCODE_TOKEN_GRACE_HOURS={self.token_grace_hours}",
            f"DARKCODE_PERMISSION_MODE={self.permission_mode}",
            f"DARKCODE_RATE_LIMIT_ATTEMPTS={self.rate_limit_attempts}",
            f"DARKCODE_RATE_LIMIT_WINDOW={self.rate_limit_window}",
        ]

        # Save browse_dir if set
        if self.browse_dir:
            lines.append(f"DARKCODE_BROWSE_DIR={self.browse_dir}")

        # Save bound device if set
        if self.bound_device_id:
            lines.append(f"DARKCODE_BOUND_DEVICE_ID={self.bound_device_id}")

        # Save custom TLS paths if set
        if self.tls_cert_path:
            lines.append(f"DARKCODE_TLS_CERT_PATH={self.tls_cert_path}")
        if self.tls_key_path:
            lines.append(f"DARKCODE_TLS_KEY_PATH={self.tls_key_path}")

        env_file.write_text("\n".join(lines) + "\n")
        env_file.chmod(0o600)

    @classmethod
    def load(cls) -> "ServerConfig":
        """Load configuration from file.

        Checks both new location (~/darkcode/.darkcode/.env) and
        legacy location (~/.darkcode/.env) for backwards compatibility.
        """
        # New location: ~/darkcode/.darkcode/.env
        new_config_dir = Path.home() / "darkcode" / ".darkcode"
        new_env_file = new_config_dir / ".env"

        # Legacy location: ~/.darkcode/.env
        legacy_config_dir = Path.home() / ".darkcode"
        legacy_env_file = legacy_config_dir / ".env"

        if new_env_file.exists():
            return cls(_env_file=str(new_env_file))
        elif legacy_env_file.exists():
            # Load from legacy location but config will save to new location
            return cls(_env_file=str(legacy_env_file))
        return cls()

    def get_local_ips(self) -> list[dict]:
        """Get all local IP addresses."""
        ips = []
        try:
            for iface in socket.getaddrinfo(socket.gethostname(), None):
                if iface[0] == socket.AF_INET:
                    ip = iface[4][0]
                    if not ip.startswith("127."):
                        ips.append({"name": "local", "address": ip})
        except Exception:
            pass

        # Also try getting the default route IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if not any(i["address"] == ip for i in ips):
                ips.insert(0, {"name": "default", "address": ip})
        except Exception:
            pass

        return ips

    def get_tailscale_ip(self) -> Optional[str]:
        """Get Tailscale IP if available."""
        try:
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_tailscale_hostname(self) -> Optional[str]:
        """Get Tailscale hostname if available."""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                dns_name = data.get("Self", {}).get("DNSName", "")
                return dns_name.rstrip(".") if dns_name else None
        except Exception:
            pass
        return None
