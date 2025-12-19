"""WebSocket server for DarkCode Agent."""

import asyncio
import hashlib
import json
import logging
import os
import ssl
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple
from pathlib import Path

# Logger for this module
logger = logging.getLogger(__name__)

import websockets
from websockets.server import WebSocketServerProtocol
from websockets.http import Headers
from websockets.http11 import Response

# Suppress noisy websockets handshake errors (TLS mismatch, InvalidUpgrade, etc.)
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)
logging.getLogger("websockets.protocol").setLevel(logging.CRITICAL)
logging.getLogger("websockets").setLevel(logging.CRITICAL)

from darkcode_server.config import ServerConfig
from darkcode_server.security import (
    CertificateManager,
    GuestAccessManager,
    PersistentRateLimiter,
    TokenManager,
)


class ServerState(Enum):
    """Server operational states."""
    AWAKE = "awake"          # Normal operation, accepting connections
    SLEEPING = "sleeping"    # Idle timeout, only bound device can wake
    LOCKED = "locked"        # Bound to device, rejecting others


class ChatHistory:
    """Persistent chat history storage."""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self, session_id: str) -> Path:
        """Get the file path for a session's chat history."""
        # Use a hash of the session_id for the filename
        safe_name = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        return self.sessions_dir / f"{safe_name}.json"

    def load(self, session_id: str) -> list[dict]:
        """Load chat history for a session."""
        file_path = self._get_session_file(session_id)
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    return data.get("messages", [])
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def save_message(self, session_id: str, message: dict):
        """Append a message to the chat history."""
        file_path = self._get_session_file(session_id)

        # Load existing messages
        messages = self.load(session_id)
        messages.append({
            **message,
            "timestamp": time.time()
        })

        # Keep only last 1000 messages per session
        if len(messages) > 1000:
            messages = messages[-1000:]

        # Save
        try:
            with open(file_path, "w") as f:
                json.dump({"session_id": session_id, "messages": messages}, f)
        except IOError:
            pass  # Ignore save errors

    def list_sessions(self) -> list[dict]:
        """List all saved sessions with metadata."""
        sessions = []
        for file_path in self.sessions_dir.glob("*.json"):
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    session_id = data.get("session_id", "")
                    messages = data.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        sessions.append({
                            "session_id": session_id,
                            "message_count": len(messages),
                            "last_active": last_msg.get("timestamp", 0),
                            "preview": last_msg.get("content", "")[:100] if "content" in last_msg else ""
                        })
            except (json.JSONDecodeError, IOError):
                continue
        return sorted(sessions, key=lambda x: x.get("last_active", 0), reverse=True)

    def delete(self, session_id: str):
        """Delete a session's chat history."""
        file_path = self._get_session_file(session_id)
        file_path.unlink(missing_ok=True)


@dataclass
class Session:
    """A Claude Code session."""

    id: str
    websocket: WebSocketServerProtocol
    device_id: str = ""  # Device fingerprint
    process: Optional[subprocess.Popen] = None
    working_dir: Path = field(default_factory=Path.cwd)
    client_ip: str = "unknown"
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    message_count: int = 0
    is_processing: bool = False
    buffer: str = ""
    # Guest session info
    is_guest: bool = False
    guest_code: str = ""
    guest_name: str = ""
    permission_level: str = "full"  # "full" or "read_only"
    # Chat history
    chat_session_id: str = ""  # Persistent chat session ID for resuming
    # Claude session ID for --resume functionality
    claude_session_id: str = ""  # Claude Code session to resume

    def __post_init__(self):
        self.working_dir = Path(self.working_dir)


def _decode_claude_project_path(encoded_name: str) -> str:
    """Decode a Claude project directory name to the actual filesystem path.

    Claude Code encodes paths by replacing / and . with -
    e.g., /Users/foo/hakc.dev -> -Users-foo-hakc-dev
    But directory names with dashes stay as dashes:
    e.g., /Users/foo/android-app -> -Users-foo-android-app

    We need to find which actual path this corresponds to by trying all combinations.
    """
    # Start by trying simple / replacement
    simple_decoded = encoded_name.replace("-", "/")
    if simple_decoded.startswith("//"):
        simple_decoded = simple_decoded[1:]

    # If that path exists, we're done
    if Path(simple_decoded).exists():
        return simple_decoded

    # Otherwise, we need to try variations
    # Split into parts and try reconstructing with / or . or - at various positions
    parts = encoded_name.split("-")
    if parts and parts[0] == "":
        parts = parts[1:]  # Remove leading empty string from "-Users-..."

    # Try all combinations and collect valid paths
    def try_combinations(idx: int, current_path: str, results: list):
        if idx >= len(parts):
            if current_path and Path(current_path).exists():
                results.append(current_path)
            return

        part = parts[idx]

        # Option 1: Add as new directory segment (/)
        if current_path:
            new_path = f"{current_path}/{part}"
        else:
            new_path = f"/{part}"
        try_combinations(idx + 1, new_path, results)

        # Option 2: Add as extension/continuation with dot (.)
        if current_path:
            dotted_path = f"{current_path}.{part}"
            try_combinations(idx + 1, dotted_path, results)

        # Option 3: Add as continuation with dash (-) - for directory names with dashes
        if current_path:
            dashed_path = f"{current_path}-{part}"
            try_combinations(idx + 1, dashed_path, results)

    results: list[str] = []
    try_combinations(0, "", results)

    if results:
        # Return the longest valid path (most specific match)
        return max(results, key=len)

    # Fallback: return simple decoded even if it doesn't exist
    return simple_decoded


def get_claude_version() -> str:
    """Get Claude Code CLI version."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse version from output like "claude 2.0.37"
            output = result.stdout.strip()
            if output.startswith("claude "):
                return output.split()[1]
            return output
    except Exception:
        pass
    return "unknown"


def list_claude_sessions(working_dir: Path, limit: int = 50) -> list[dict]:
    """List available Claude Code sessions across all projects.

    Scans project directories in ~/.claude/projects/ to find sessions.
    Returns sessions sorted by last modified time (most recent first).
    Limited to most recent sessions for performance.

    Args:
        working_dir: The working directory (used for context)
        limit: Maximum number of sessions to return (default 50)
    """
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return []

    # First, collect all session files with their mod times (fast - just stat)
    session_files = []

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue

        encoded_path = project_dir.name
        actual_path = _decode_claude_project_path(encoded_path)

        for session_file in project_dir.glob("*.jsonl"):
            # Skip agent sessions (subagent files)
            if session_file.stem.startswith("agent-"):
                continue

            try:
                stat = session_file.stat()
                if stat.st_size == 0:
                    continue
                session_files.append((session_file, stat, project_dir, actual_path))
            except (IOError, OSError):
                continue

    # Sort by modification time (newest first) and take only the limit
    session_files.sort(key=lambda x: x[1].st_mtime, reverse=True)
    session_files = session_files[:limit]

    sessions = []

    for session_file, stat, project_dir, actual_path in session_files:
        try:
            preview = ""
            message_count = 0
            session_id = session_file.stem

            # Check if there's a subdirectory with same name (active session)
            has_subdir = (project_dir / session_id).is_dir()

            # Single pass through file: find preview and count messages
            with open(session_file, "r") as f:
                lines_checked = 0
                for line in f:
                    lines_checked += 1
                    # Limit lines scanned for preview, but count all messages
                    if lines_checked > 200:
                        # After 200 lines, just count without parsing
                        message_count += line.count('"type": "user"') + line.count('"type": "assistant"')
                        continue

                    try:
                        data = json.loads(line)
                        msg_type = data.get("type")

                        # Count user/assistant messages
                        if msg_type in ("user", "assistant"):
                            message_count += 1

                        # Find preview (first real user message)
                        if not preview and msg_type == "user":
                            msg = data.get("message", {})
                            content = msg.get("content", [])
                            if isinstance(content, list) and content:
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        text = block.get("text", "").strip()
                                        if not text.startswith("<") and len(text) > 5:
                                            preview = text.split("\n")[0][:120]
                                            break
                    except json.JSONDecodeError:
                        continue

            sessions.append({
                "sessionId": session_id,
                "lastModified": int(stat.st_mtime * 1000),
                "size": stat.st_size,
                "preview": preview,
                "isActive": has_subdir,
                "projectPath": actual_path,
                "messageCount": message_count,  # For Whisper Sync
            })
        except (IOError, OSError):
            continue

    # Sort: active sessions first, then by last modified (most recent first)
    sessions.sort(key=lambda x: (not x["isActive"], -x["lastModified"]))
    return sessions[:30]  # Limit to 30 most recent


class DarkCodeServer:
    """WebSocket server that bridges mobile app to Claude Code CLI."""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig.load()
        self.sessions: dict[str, Session] = {}
        self.ip_session_count: dict[str, int] = {}
        self._server = None
        self._running = False

        # Security managers
        self._rate_limiter = PersistentRateLimiter(
            db_path=self.config.config_dir / "security.db",
            max_attempts=self.config.rate_limit_attempts,
            window_seconds=self.config.rate_limit_window,
        )

        self._token_manager: Optional[TokenManager] = None
        if self.config.token_rotation_days > 0:
            self._token_manager = TokenManager(
                db_path=self.config.config_dir / "tokens.db",
                rotation_days=self.config.token_rotation_days,
                grace_hours=self.config.token_grace_hours,
            )
            # Initialize with current token
            self._token_manager.set_current_token(self.config.token)

        self._cert_manager: Optional[CertificateManager] = None
        if self.config.tls_enabled:
            self._cert_manager = CertificateManager(
                cert_dir=self.config.config_dir / "certs"
            )

        # Guest access manager (always available)
        self._guest_manager = GuestAccessManager(
            db_path=self.config.config_dir / "guests.db"
        )

        # Chat history persistence
        self._chat_history = ChatHistory(
            sessions_dir=self.config.config_dir / "chat_sessions"
        )

        # Device binding state
        self._state = ServerState.AWAKE
        self._bound_device_id: Optional[str] = None
        self._last_activity = time.time()
        self._idle_check_task: Optional[asyncio.Task] = None
        self._rotation_check_task: Optional[asyncio.Task] = None

        # Load bound device from config
        if self.config.device_lock and self.config.bound_device_id:
            self._bound_device_id = self.config.bound_device_id
            self._state = ServerState.LOCKED

        # Web admin handler (lazy loaded)
        self._web_admin = None

    def _generate_device_id(self, client_ip: str, user_agent: str = "", device_info: dict = None) -> str:
        """Generate a unique device fingerprint.

        SECURITY: Device fingerprint combines multiple factors. If device_info
        is not provided, we use a salted hash of IP + user_agent which is weaker
        but still requires the attacker to know both values.
        """
        # Sanitize inputs to prevent log injection
        def sanitize(s: str) -> str:
            if not s:
                return ""
            # Remove control characters and limit length
            return "".join(c for c in s[:256] if c.isprintable())

        factors = []
        if device_info:
            # Prefer hardware-based identifiers
            factors.extend([
                sanitize(device_info.get("device_id", "")),
                sanitize(device_info.get("android_id", "")),
                sanitize(device_info.get("model", "")),
                sanitize(device_info.get("fingerprint", "")),  # Build fingerprint
            ])

        factors.append(sanitize(user_agent))

        # Filter empty strings
        data = "|".join(f for f in factors if f)

        if not data:
            # Fallback: use IP + server secret as salt (weaker but better than IP alone)
            # This prevents simple IP spoofing from working
            data = f"{client_ip}|{self.config.token[:8]}"

        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _bind_device(self, device_id: str):
        """Bind server to a device."""
        self._bound_device_id = device_id
        self._state = ServerState.LOCKED
        # Persist to config
        self.config.bound_device_id = device_id
        self.config.save()

    def _is_bound_device(self, device_id: str) -> bool:
        """Check if device is the bound device."""
        if not self._bound_device_id:
            return True  # No device bound yet
        return device_id == self._bound_device_id

    def _update_activity(self):
        """Update last activity timestamp."""
        self._last_activity = time.time()
        if self._state == ServerState.SLEEPING:
            self._state = ServerState.LOCKED if self._bound_device_id else ServerState.AWAKE

    async def _idle_monitor(self):
        """Monitor for idle timeout."""
        while self._running:
            await asyncio.sleep(30)  # Check every 30 seconds

            if self.config.idle_timeout <= 0:
                continue

            idle_time = time.time() - self._last_activity

            if idle_time > self.config.idle_timeout and self._state != ServerState.SLEEPING:
                if not self.sessions:  # Only sleep if no active sessions
                    self._state = ServerState.SLEEPING

    async def _token_rotation_monitor(self):
        """Monitor for token rotation."""
        while self._running:
            await asyncio.sleep(3600)  # Check every hour

            if self._token_manager and self._token_manager.should_rotate():
                new_token = self._token_manager.rotate()
                # Update config with new token
                self.config.token = new_token
                self.config.save()
                # Note: Old tokens valid for grace_hours

    async def _process_request(self, connection, request):
        """Process HTTP requests before WebSocket upgrade.

        This allows serving the web admin dashboard on /admin while
        still handling WebSocket connections on the same port.

        Note: websockets 13+ passes (connection, request) instead of (path, headers)
        and expects a Response object, not a tuple.
        """
        # Extract path and headers from the request object
        # Handle both old and new websockets API
        if hasattr(request, 'path'):
            path = request.path
            request_headers = request.headers
        else:
            # Old API - request is actually path string
            path = str(connection) if isinstance(connection, str) else getattr(connection, 'path', '/')
            request_headers = request if hasattr(request, 'get') else {}

        # Serve favicon.ico
        if isinstance(path, str) and path == '/favicon.ico':
            try:
                from darkcode_server.web_admin import serve_favicon
                status, resp_headers, resp_body = serve_favicon()
                header_list = [(k, v) for k, v in resp_headers.items()]
                return Response(status, "OK", Headers(header_list), resp_body)
            except ImportError:
                return Response(404, "Not Found", Headers([]), b"")

        # Check if web admin is disabled
        if getattr(self.config, 'web_admin_disabled', False):
            # Return None to let websockets handle it normally
            # This may result in 426 for non-WS requests, which is fine
            return None

        # Handle admin dashboard requests (non-WebSocket HTTP)
        if isinstance(path, str) and path.startswith('/admin'):
            # Initialize web admin handler if needed
            if self._web_admin is None:
                try:
                    from darkcode_server.web_admin import WebAdminHandler
                    self._web_admin = WebAdminHandler(self.config, self)
                except ImportError:
                    return Response(404, "Not Found", Headers([]), b"Web admin not available")

            # Determine HTTP method
            method = 'GET'
            content_length = request_headers.get('Content-Length', '0')
            if int(content_length) > 0:
                method = 'POST'

            # Build headers dict
            headers = {str(k): str(v) for k, v in request_headers.items()}

            # Handle the request
            status, resp_headers, resp_body = self._web_admin.handle_request(
                path, method, headers, b''
            )

            # Build Response object for websockets 13+
            from http import HTTPStatus
            try:
                reason = HTTPStatus(status).phrase
            except ValueError:
                reason = "Unknown"

            header_list = [(k, v) for k, v in resp_headers.items()]
            return Response(status, reason, Headers(header_list), resp_body)

        # Check if this is a WebSocket upgrade request
        # If not, return a friendly HTTP response instead of letting websockets raise InvalidUpgrade
        connection_header = request_headers.get('Connection', '').lower() if hasattr(request_headers, 'get') else ''
        upgrade_header = request_headers.get('Upgrade', '').lower() if hasattr(request_headers, 'get') else ''

        if 'upgrade' not in connection_header or upgrade_header != 'websocket':
            # Non-WebSocket HTTP request - return a simple response
            # This prevents InvalidUpgrade errors from browser auto-refresh, health checks, etc.
            html = b"""<!DOCTYPE html>
<html><head><title>DarkCode Server</title></head>
<body style="font-family: system-ui; background: #1a1a2e; color: #eee; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
<div style="text-align: center;">
<h1 style="color: #00d4ff;">DarkCode Server</h1>
<p>WebSocket server running. Use the DarkCode app to connect.</p>
<p><a href="/admin" style="color: #00d4ff;">Web Admin Dashboard</a></p>
</div></body></html>"""
            return Response(
                200, "OK",
                Headers([
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(html))),
                    ("Cache-Control", "no-cache"),
                ]),
                html
            )

        # For WebSocket paths, return None to continue with upgrade
        return None

    async def start(self):
        """Start the WebSocket server."""
        self._running = True

        # Prepare SSL context if TLS enabled
        ssl_context = None
        if self.config.tls_enabled and self._cert_manager:
            # Use custom certs if provided, otherwise generate
            if self.config.tls_cert_path and self.config.tls_key_path:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(
                    certfile=str(self.config.tls_cert_path),
                    keyfile=str(self.config.tls_key_path),
                )
            else:
                # Generate self-signed cert with local IPs
                local_ips = [ip["address"] for ip in self.config.get_local_ips()]
                tailscale_ip = self.config.get_tailscale_ip()
                if tailscale_ip:
                    local_ips.append(tailscale_ip)

                self._cert_manager.generate_server_cert(
                    hostname=self.config.server_name,
                    san_ips=local_ips,
                )
                ssl_context = self._cert_manager.get_ssl_context(
                    require_client_cert=self.config.mtls_enabled
                )

        self._server = await websockets.serve(
            self._handle_connection,
            self.config.bind_host,  # Use bind_host which respects local_only
            self.config.port,
            ssl=ssl_context,
            ping_interval=self.config.ping_interval,
            ping_timeout=self.config.ping_timeout,
            process_request=self._process_request,  # Handle HTTP admin requests
        )

        # Start idle monitor if timeout is configured
        if self.config.idle_timeout > 0:
            self._idle_check_task = asyncio.create_task(self._idle_monitor())

        # Start token rotation monitor
        if self._token_manager:
            self._rotation_check_task = asyncio.create_task(self._token_rotation_monitor())

        return self._server

    async def stop(self):
        """Stop the server and cleanup."""
        self._running = False

        if self._idle_check_task:
            self._idle_check_task.cancel()
            try:
                await self._idle_check_task
            except asyncio.CancelledError:
                pass

        if self._rotation_check_task:
            self._rotation_check_task.cancel()
            try:
                await self._rotation_check_task
            except asyncio.CancelledError:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Cleanup sessions
        for session in list(self.sessions.values()):
            await self._destroy_session(session)

    @property
    def state(self) -> ServerState:
        """Current server state."""
        return self._state

    @property
    def bound_device(self) -> Optional[str]:
        """Bound device ID if any."""
        return self._bound_device_id

    def unbind_device(self):
        """Unbind the current device (requires restart or explicit call)."""
        self._bound_device_id = None
        self._state = ServerState.AWAKE
        self.config.bound_device_id = None
        self.config.save()

    async def _handle_connection(self, websocket: WebSocketServerProtocol):
        """Handle a new WebSocket connection."""
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"

        # mTLS: Extract device ID from client certificate if available
        mtls_device_id: Optional[str] = None
        if self.config.mtls_enabled and self._cert_manager:
            # Get client certificate from SSL context
            ssl_object = websocket.transport.get_extra_info('ssl_object')
            if ssl_object:
                try:
                    client_cert = ssl_object.getpeercert(binary_form=True)
                    if client_cert:
                        mtls_device_id = self._cert_manager.verify_client_cert(client_cert)
                except Exception:
                    pass

            if not mtls_device_id:
                await websocket.close(1008, "Client certificate required")
                return

        # Check session limit
        if self.ip_session_count.get(client_ip, 0) >= self.config.max_sessions_per_ip:
            await websocket.close(1008, "Too many concurrent sessions")
            return

        session: Optional[Session] = None
        authenticated = False
        device_id: Optional[str] = None

        try:
            async for message in websocket:
                try:
                    msg = json.loads(message)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON"
                    }))
                    continue

                if not authenticated:
                    if msg.get("type") == "auth":
                        # Persistent rate limiting
                        allowed, remaining = self._rate_limiter.check_rate_limit(client_ip, "ip")
                        if not allowed:
                            await websocket.send(json.dumps({
                                "type": "auth_result",
                                "success": False,
                                "message": "Too many attempts. Try again later.",
                                "retry_after": self.config.rate_limit_window,
                            }))
                            continue

                        # Check for guest code first
                        guest_code = msg.get("guest_code", "")
                        is_guest = False
                        guest_info = None
                        permission_level = "full"

                        if guest_code:
                            # Guest code authentication
                            code_valid, guest_info = self._guest_manager.verify_code(guest_code)
                            if not code_valid:
                                self._rate_limiter.record_attempt(client_ip, "ip", success=False)
                                error_msg = "Invalid guest code"
                                if guest_info and guest_info.get("error") == "expired":
                                    error_msg = "Guest code has expired"
                                elif guest_info and guest_info.get("error") == "max_uses_reached":
                                    error_msg = "Guest code has reached maximum uses"
                                await websocket.send(json.dumps({
                                    "type": "auth_result",
                                    "success": False,
                                    "message": error_msg,
                                }))
                                continue
                            is_guest = True
                            permission_level = guest_info.get("permission_level", "full")
                        else:
                            # Standard token authentication
                            token = msg.get("token", "")
                            token_valid, token_status = self._verify_token_with_manager(token)
                            if not token_valid:
                                self._rate_limiter.record_attempt(client_ip, "ip", success=False)
                                error_message = "Invalid token"
                                if token_status == "token_expired":
                                    error_message = "Token expired. Request new token from server."
                                await websocket.send(json.dumps({
                                    "type": "auth_result",
                                    "success": False,
                                    "message": error_message,
                                }))
                                continue

                        # Generate device fingerprint (use mTLS device ID if available)
                        if mtls_device_id:
                            device_id = mtls_device_id
                        else:
                            device_info = msg.get("device_info", {})
                            device_id = self._generate_device_id(
                                client_ip,
                                msg.get("user_agent", ""),
                                device_info,
                            )

                        # Check device binding (skip for guest access)
                        if self.config.device_lock and not is_guest:
                            if self._state == ServerState.SLEEPING:
                                # Server is sleeping - only bound device can wake it
                                if not self._is_bound_device(device_id):
                                    await websocket.send(json.dumps({
                                        "type": "auth_result",
                                        "success": False,
                                        "message": "Server is sleeping. Only the bound device can connect.",
                                        "state": "sleeping",
                                    }))
                                    continue
                                # Wake up!
                                self._update_activity()

                            elif self._bound_device_id and not self._is_bound_device(device_id):
                                # Wrong device trying to connect
                                self._rate_limiter.record_attempt(device_id, "device", success=False)
                                await websocket.send(json.dumps({
                                    "type": "auth_result",
                                    "success": False,
                                    "message": "Server is locked to another device.",
                                    "state": "locked",
                                }))
                                continue

                            elif not self._bound_device_id:
                                # First connection - bind this device
                                self._bind_device(device_id)

                        # Auth passed
                        authenticated = True
                        self._rate_limiter.record_attempt(client_ip, "ip", success=True)
                        self._update_activity()

                        # Record guest code usage
                        if is_guest:
                            self._guest_manager.use_code(guest_code, device_id, client_ip)

                        # Create session
                        import uuid
                        session_id = str(uuid.uuid4())
                        session = Session(
                            id=session_id,
                            websocket=websocket,
                            device_id=device_id,
                            working_dir=self.config.working_dir,
                            client_ip=client_ip,
                            is_guest=is_guest,
                            guest_code=guest_code if is_guest else "",
                            guest_name=guest_info.get("name", "") if guest_info else "",
                            permission_level=permission_level,
                        )
                        self.sessions[session_id] = session
                        self.ip_session_count[client_ip] = (
                            self.ip_session_count.get(client_ip, 0) + 1
                        )

                        # Start Claude process
                        await self._start_claude_process(session)

                        # Get Claude version
                        claude_version = get_claude_version()

                        auth_response = {
                            "type": "auth_result",
                            "success": True,
                            "sessionId": session_id,
                            "workingDir": str(self.config.working_dir),
                            "browseDir": str(self.config.effective_browse_dir),
                            "deviceBound": self.config.device_lock,
                            "state": self._state.value,
                            "isGuest": is_guest,
                            "permissionLevel": permission_level,
                            "claudeVersion": claude_version,
                            "serverName": self.config.server_name,
                        }
                        if is_guest and guest_info:
                            auth_response["guestName"] = guest_info.get("name", "")
                            auth_response["guestExpiresAt"] = guest_info.get("expires_at")
                            auth_response["guestUsesRemaining"] = (
                                guest_info.get("max_uses", 0) - guest_info.get("use_count", 0)
                                if guest_info.get("max_uses") else None
                            )
                        await websocket.send(json.dumps(auth_response))
                    else:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": "Not authenticated",
                        }))
                    continue

                # Handle authenticated messages
                if session:
                    self._update_activity()
                    await self._handle_message(session, msg)

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if session:
                await self._destroy_session(session)
                count = self.ip_session_count.get(client_ip, 1) - 1
                if count <= 0:
                    self.ip_session_count.pop(client_ip, None)
                else:
                    self.ip_session_count[client_ip] = count

    async def _start_claude_process(self, session: Session, resume_session_id: str = None):
        """Start the Claude Code CLI process.

        SECURITY: Uses validated working directory from config.
        Uses -p (print mode) with stream-json for bidirectional streaming.

        Args:
            session: The session to start Claude for
            resume_session_id: Optional Claude session ID to resume (for handoffs)
        """
        try:
            # Use session's working directory if set (e.g., when resuming a session),
            # otherwise fall back to config's validated working directory
            if session.working_dir and session.working_dir.exists():
                working_dir = session.working_dir
            else:
                working_dir = self.config.safe_working_dir

            # Build command with streaming and permission handling
            cmd = [
                "claude",
                "-p",  # Print mode for non-interactive streaming
                "--output-format", "stream-json",
                "--input-format", "stream-json",
                "--verbose",  # Required for stream-json
                "--include-partial-messages",  # Enable streaming deltas
                "--permission-mode", self.config.permission_mode,
            ]

            # Add resume flag if resuming a session (session handoff)
            if resume_session_id:
                cmd.extend(["--resume", resume_session_id])

            session.process = subprocess.Popen(
                cmd,
                cwd=str(working_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # Start output reader task
            asyncio.create_task(self._read_output(session))

            await session.websocket.send(json.dumps({
                "type": "status",
                "status": "ready",
                "sessionId": session.id,
            }))

        except Exception as e:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Failed to start Claude: {e}",
                "recoverable": False,
            }))

    async def _read_output(self, session: Session):
        """Read output from Claude process."""
        if not session.process or not session.process.stdout:
            return

        loop = asyncio.get_event_loop()

        def read_line():
            if session.process and session.process.stdout:
                try:
                    return session.process.stdout.readline()
                except (IOError, OSError):
                    return ""
            return ""

        while session.process and session.process.poll() is None:
            try:
                line = await loop.run_in_executor(None, read_line)
                if not line:
                    # Check if process died
                    if session.process and session.process.poll() is not None:
                        break
                    await asyncio.sleep(0.01)
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    parsed = json.loads(line)
                    await self._handle_claude_output(session, parsed)
                except json.JSONDecodeError:
                    await session.websocket.send(json.dumps({
                        "type": "claude_output",
                        "raw": line,
                    }))

            except Exception:
                break

        # Process has exited - notify client and offer recovery
        exit_code = session.process.poll() if session.process else -1
        session.is_processing = False

        # Read any stderr output
        stderr_output = ""
        if session.process and session.process.stderr:
            try:
                stderr_output = session.process.stderr.read() or ""
            except Exception:
                pass

        # Send error to client with recovery action
        try:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Claude process exited (code {exit_code})" + (f": {stderr_output[:200]}" if stderr_output else ""),
                "recoverable": True,
                "action": "reconnect",
            }))
            await session.websocket.send(json.dumps({
                "type": "status",
                "status": "closed",
            }))
        except Exception:
            pass  # WebSocket might already be closed

    async def _handle_claude_output(self, session: Session, msg: dict):
        """Handle parsed output from Claude."""
        msg_type = msg.get("type", "")

        if msg_type == "stream_event":
            # Handle streaming deltas for real-time text updates
            event = msg.get("event", {})
            event_type = event.get("type", "")

            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        await session.websocket.send(json.dumps({
                            "type": "stream_delta",
                            "text": text,
                            "index": event.get("index", 0),
                        }))

            elif event_type == "content_block_start":
                content_block = event.get("content_block", {})
                await session.websocket.send(json.dumps({
                    "type": "stream_start",
                    "index": event.get("index", 0),
                    "blockType": content_block.get("type", "text"),
                }))

            elif event_type == "content_block_stop":
                await session.websocket.send(json.dumps({
                    "type": "stream_stop",
                    "index": event.get("index", 0),
                }))

            elif event_type == "message_start":
                await session.websocket.send(json.dumps({
                    "type": "message_start",
                }))

            elif event_type == "message_stop":
                await session.websocket.send(json.dumps({
                    "type": "message_stop",
                }))

        elif msg_type == "assistant":
            # Extract text from Claude's content array structure
            # Claude returns: {"message": {"content": [{"type": "text", "text": "..."}]}}
            raw_content = msg.get("message", {}).get("content") or msg.get("content")

            # Parse content array to extract text
            if isinstance(raw_content, list):
                # Content is array of blocks like [{"type": "text", "text": "..."}]
                text_parts = []
                for block in raw_content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            # Tool use blocks are handled separately
                            pass
                content = "\n".join(text_parts)
            elif isinstance(raw_content, str):
                content = raw_content
            else:
                content = str(raw_content) if raw_content else ""

            if content:
                await session.websocket.send(json.dumps({
                    "type": "claude_message",
                    "role": "assistant",
                    "content": content,
                    "timestamp": int(time.time() * 1000),
                }))

                # Save assistant message to chat history
                if session.chat_session_id:
                    self._chat_history.save_message(session.chat_session_id, {
                        "role": "assistant",
                        "content": content,
                    })

        elif msg_type == "tool_use":
            await session.websocket.send(json.dumps({
                "type": "tool_use",
                "id": msg.get("tool_use_id") or msg.get("id"),
                "name": msg.get("name") or msg.get("tool_name"),
                "input": msg.get("input") or msg.get("parameters"),
            }))

        elif msg_type == "tool_result":
            await session.websocket.send(json.dumps({
                "type": "tool_result",
                "id": msg.get("tool_use_id") or msg.get("id"),
                "content": msg.get("content") or msg.get("result"),
                "isError": msg.get("is_error", False),
            }))

        elif msg_type == "result":
            session.is_processing = False
            await session.websocket.send(json.dumps({
                "type": "status",
                "status": "complete",
                "cost": msg.get("total_cost_usd") or msg.get("cost_usd"),
                "duration": msg.get("duration_ms"),
                "result": msg.get("result"),
            }))

        elif msg_type == "system":
            # System init message with session info
            subtype = msg.get("subtype", "")
            if subtype == "init":
                await session.websocket.send(json.dumps({
                    "type": "system_init",
                    "sessionId": msg.get("session_id"),
                    "model": msg.get("model"),
                    "tools": msg.get("tools", []),
                }))
            else:
                await session.websocket.send(json.dumps({
                    "type": "system",
                    "subtype": subtype,
                    "data": msg,
                }))

        else:
            # Forward unknown message types
            await session.websocket.send(json.dumps({
                "type": "claude_output",
                "parsed": msg,
            }))

    def _is_process_alive(self, session: Session) -> bool:
        """Check if the Claude process is still running."""
        if not session.process:
            return False
        return session.process.poll() is None

    async def _write_to_process(self, session: Session, text: str, is_json: bool = False) -> bool:
        """Write to Claude process stdin with error handling.

        Args:
            session: The session with the Claude process
            text: The text to write (user message content)
            is_json: If True, text is already JSON-formatted; if False, wrap in user message

        Returns True if write succeeded, False otherwise.
        """
        if not session.process or not session.process.stdin:
            return False

        # Check if process is still alive
        if not self._is_process_alive(session):
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Claude process has terminated. Please reconnect.",
                "recoverable": True,
                "action": "reconnect",
            }))
            return False

        try:
            # Format as stream-json input if not already JSON
            if is_json:
                data = text
            else:
                # Wrap in Claude's expected stream-json input format
                data = json.dumps({
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": text
                    }
                })

            session.process.stdin.write(data + "\n")
            session.process.stdin.flush()
            return True
        except BrokenPipeError:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Claude process closed unexpectedly. Please reconnect.",
                "recoverable": True,
                "action": "reconnect",
            }))
            return False
        except (IOError, OSError) as e:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Failed to communicate with Claude: {e}",
                "recoverable": True,
                "action": "reconnect",
            }))
            return False

    async def _handle_message(self, session: Session, msg: dict):
        """Handle an authenticated message.

        SECURITY: All user input is validated before being passed to subprocess.
        """
        msg_type = msg.get("type", "")

        # Max message size (1MB should be plenty for any prompt)
        MAX_MESSAGE_SIZE = 1024 * 1024

        if msg_type == "send_message":
            text = msg.get("text", "")

            # Validate message
            if not isinstance(text, str):
                await session.websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid message format",
                }))
                return

            if len(text) > MAX_MESSAGE_SIZE:
                await session.websocket.send(json.dumps({
                    "type": "error",
                    "message": f"Message too large (max {MAX_MESSAGE_SIZE} bytes)",
                }))
                return

            if text:
                # Check process health and write
                if await self._write_to_process(session, text):
                    session.is_processing = True
                    session.last_active = time.time()
                    session.message_count += 1

                    # Save user message to chat history
                    if session.chat_session_id:
                        self._chat_history.save_message(session.chat_session_id, {
                            "role": "user",
                            "content": text,
                        })

                    await session.websocket.send(json.dumps({
                        "type": "status",
                        "status": "processing",
                    }))

        elif msg_type == "send_message_with_files":
            # Handle message with file attachments
            text = msg.get("text", "")
            files = msg.get("files", [])

            # Validate
            if not isinstance(text, str):
                text = ""
            if not isinstance(files, list):
                files = []

            # Process files - save them and build context
            file_descriptions = []
            saved_files = []

            for file_info in files[:5]:  # Max 5 files
                try:
                    name = file_info.get("name", "file")
                    content = file_info.get("content", "")
                    is_base64 = file_info.get("isBase64", False)
                    mime_type = file_info.get("mimeType", "application/octet-stream")

                    # Sanitize filename
                    safe_name = "".join(c for c in name if c.isalnum() or c in "._-")[:100]
                    if not safe_name:
                        safe_name = "uploaded_file"

                    # Save to uploads subdirectory
                    uploads_dir = session.working_dir / ".darkcode_uploads"
                    uploads_dir.mkdir(exist_ok=True)

                    file_path = uploads_dir / safe_name

                    # Handle base64 vs text content
                    if is_base64:
                        import base64
                        try:
                            decoded = base64.b64decode(content)
                            file_path.write_bytes(decoded)
                        except Exception:
                            continue
                    else:
                        file_path.write_text(content, encoding="utf-8")

                    saved_files.append(str(file_path))

                    # Build description for Claude
                    if mime_type.startswith("image/"):
                        file_descriptions.append(f"[Image attached: {safe_name} at {file_path}]")
                    elif mime_type.startswith("text/") or not is_base64:
                        # Include text content directly for Claude to see
                        preview = content[:2000] if len(content) > 2000 else content
                        file_descriptions.append(f"[File: {safe_name}]\n```\n{preview}\n```")
                    else:
                        file_descriptions.append(f"[Binary file attached: {safe_name} at {file_path}]")

                except Exception as e:
                    logger.warning(f"Failed to process file: {e}")
                    continue

            # Build the full message
            full_message = text
            if file_descriptions:
                files_context = "\n\n".join(file_descriptions)
                if text:
                    full_message = f"{text}\n\n--- Attached Files ---\n{files_context}"
                else:
                    full_message = f"--- Attached Files ---\n{files_context}"

            if full_message:
                if await self._write_to_process(session, full_message):
                    session.is_processing = True
                    session.last_active = time.time()
                    session.message_count += 1

                    # Save to chat history
                    if session.chat_session_id:
                        self._chat_history.save_message(session.chat_session_id, {
                            "role": "user",
                            "content": text if text else "(files attached)",
                            "files": saved_files,
                        })

                    await session.websocket.send(json.dumps({
                        "type": "status",
                        "status": "processing",
                    }))

        elif msg_type == "abort":
            if session.process and self._is_process_alive(session):
                try:
                    session.process.send_signal(subprocess.signal.SIGINT)
                except (ProcessLookupError, OSError):
                    pass  # Process already dead
                session.is_processing = False
                await session.websocket.send(json.dumps({
                    "type": "status",
                    "status": "aborted",
                }))

        elif msg_type == "accept_edit":
            await self._write_to_process(session, "y")

        elif msg_type == "reject_edit":
            await self._write_to_process(session, "n")

        elif msg_type == "get_session_info":
            await session.websocket.send(json.dumps({
                "type": "session_info",
                "sessionId": session.id,
                "chatSessionId": session.chat_session_id,
                "workingDir": str(session.working_dir),
                "isProcessing": session.is_processing,
                "messageCount": session.message_count,
                "processAlive": self._is_process_alive(session),
            }))

        elif msg_type == "set_chat_session":
            # Set or create a chat session ID for persistence
            chat_session_id = msg.get("chatSessionId", "")
            if chat_session_id:
                session.chat_session_id = chat_session_id
            else:
                # Generate a new one based on working dir and time
                session.chat_session_id = hashlib.sha256(
                    f"{session.working_dir}-{time.time()}".encode()
                ).hexdigest()[:16]

            await session.websocket.send(json.dumps({
                "type": "chat_session_set",
                "chatSessionId": session.chat_session_id,
            }))

        elif msg_type == "get_chat_history":
            # Return chat history for a session
            chat_session_id = msg.get("chatSessionId", session.chat_session_id)
            if chat_session_id:
                messages = self._chat_history.load(chat_session_id)
                await session.websocket.send(json.dumps({
                    "type": "chat_history",
                    "chatSessionId": chat_session_id,
                    "messages": messages,
                }))
            else:
                await session.websocket.send(json.dumps({
                    "type": "chat_history",
                    "messages": [],
                }))

        elif msg_type == "list_chat_sessions":
            # List all saved chat sessions
            sessions = self._chat_history.list_sessions()
            await session.websocket.send(json.dumps({
                "type": "chat_sessions_list",
                "sessions": sessions,
            }))

        elif msg_type == "delete_chat_session":
            # Delete a chat session
            chat_session_id = msg.get("chatSessionId", "")
            if chat_session_id:
                self._chat_history.delete(chat_session_id)
                await session.websocket.send(json.dumps({
                    "type": "chat_session_deleted",
                    "chatSessionId": chat_session_id,
                }))

        # === Claude Session Handoffs ===
        elif msg_type == "list_claude_sessions":
            # List available Claude Code sessions for handoff
            sessions_list = list_claude_sessions(session.working_dir)
            await session.websocket.send(json.dumps({
                "type": "claude_sessions_list",
                "sessions": sessions_list,
                "workingDir": str(session.working_dir),
            }))

        elif msg_type == "resume_claude_session":
            # Resume a specific Claude Code session
            claude_session_id = msg.get("sessionId", "")
            project_path = msg.get("projectPath", "")
            if not claude_session_id:
                await session.websocket.send(json.dumps({
                    "type": "error",
                    "message": "sessionId is required to resume a session",
                }))
                return

            # Kill existing Claude process if running
            if session.process and self._is_process_alive(session):
                try:
                    session.process.terminate()
                    session.process.wait(timeout=3)
                except Exception:
                    session.process.kill()

            # Store the Claude session ID for resume
            session.claude_session_id = claude_session_id

            # Update working directory if project path provided
            # Claude --resume requires being in the correct project directory
            if project_path:
                project_dir = Path(project_path)
                if project_dir.exists() and project_dir.is_dir():
                    session.working_dir = project_dir

            # Start Claude with the resume flag
            await self._start_claude_process(session, resume_session_id=claude_session_id)

            await session.websocket.send(json.dumps({
                "type": "claude_session_resumed",
                "sessionId": claude_session_id,
                "workingDir": str(session.working_dir),
            }))

        # === File Operations ===
        elif msg_type == "list_files":
            # List files in a directory
            path = msg.get("path", "")
            await self._handle_list_files(session, path)

        elif msg_type == "create_directory":
            # Create a new directory
            path = msg.get("path", "")
            await self._handle_create_directory(session, path)

        elif msg_type == "read_file":
            # Read file contents
            path = msg.get("path", "")
            await self._handle_read_file(session, path)

        elif msg_type == "delete_file":
            # Delete a file or directory
            path = msg.get("path", "")
            await self._handle_delete_file(session, path)

        # === Terminal/Bash Execution ===
        elif msg_type == "execute_bash":
            command = msg.get("command", "")
            timeout = msg.get("timeout", 30000)  # Default 30s
            logger.info(f"[BASH] Received execute_bash: {command[:100]}")
            await self._handle_execute_bash(session, command, timeout)

    async def _handle_execute_bash(self, session: Session, command: str, timeout_ms: int):
        """Execute a bash command directly and return the output.

        SECURITY: Commands are executed in the session's working directory.
        This is for terminal mode - direct shell access for the user.
        """
        if not command or not command.strip():
            await session.websocket.send(json.dumps({
                "type": "bash_output",
                "command": command,
                "output": "Error: Empty command",
                "exitCode": 1,
                "isError": True,
            }))
            return

        # Sanitize command - basic safety checks
        command = command.strip()

        # Max command length
        if len(command) > 10000:
            await session.websocket.send(json.dumps({
                "type": "bash_output",
                "command": command[:100] + "...",
                "output": "Error: Command too long",
                "exitCode": 1,
                "isError": True,
            }))
            return

        timeout_sec = min(timeout_ms / 1000, 300)  # Max 5 minutes

        try:
            import asyncio

            # Run command in working directory
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(session.working_dir),
                env={**os.environ, "TERM": "xterm-256color"},
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_sec
                )
                exit_code = process.returncode or 0

                # Combine stdout and stderr
                output = ""
                if stdout:
                    output += stdout.decode("utf-8", errors="replace")
                if stderr:
                    if output:
                        output += "\n"
                    output += stderr.decode("utf-8", errors="replace")

                response = {
                    "type": "bash_output",
                    "command": command,
                    "output": output.strip() or "(no output)",
                    "exitCode": exit_code,
                    "isError": exit_code != 0,
                    "timestamp": int(time.time() * 1000),
                }
                logger.info(f"[BASH] Sending response: exit={exit_code}, output_len={len(output)}")
                await session.websocket.send(json.dumps(response))

            except asyncio.TimeoutError:
                process.kill()
                await session.websocket.send(json.dumps({
                    "type": "bash_output",
                    "command": command,
                    "output": f"Error: Command timed out after {timeout_sec}s",
                    "exitCode": 124,  # Standard timeout exit code
                    "isError": True,
                    "timestamp": int(time.time() * 1000),
                }))

        except Exception as e:
            logger.error(f"Bash execution error: {e}")
            await session.websocket.send(json.dumps({
                "type": "bash_output",
                "command": command,
                "output": f"Error: {str(e)}",
                "exitCode": 1,
                "isError": True,
                "timestamp": int(time.time() * 1000),
            }))

    def _resolve_safe_path(self, session: Session, path: str) -> Optional[Path]:
        """Resolve a path safely within the working directory.

        Returns None if path would escape the working directory.
        """
        if not path:
            return session.working_dir

        # Resolve the path relative to working directory
        try:
            target = (session.working_dir / path).resolve()
            # Ensure it's within working directory (prevent directory traversal)
            if session.working_dir.resolve() in target.parents or target == session.working_dir.resolve():
                return target
            # Also allow if target starts with working_dir (for paths inside)
            working_resolved = session.working_dir.resolve()
            if str(target).startswith(str(working_resolved)):
                return target
        except (ValueError, OSError):
            pass
        return None

    async def _handle_list_files(self, session: Session, path: str):
        """List files in a directory."""
        target = self._resolve_safe_path(session, path)

        if not target:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Invalid path: outside working directory",
            }))
            return

        if not target.exists():
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Path does not exist: {path}",
            }))
            return

        if not target.is_dir():
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Not a directory: {path}",
            }))
            return

        try:
            files = []
            for item in sorted(target.iterdir()):
                stat = item.stat()
                files.append({
                    "name": item.name,
                    "path": str(item.relative_to(session.working_dir)),
                    "isDirectory": item.is_dir(),
                    "size": stat.st_size if item.is_file() else 0,
                    "modified": int(stat.st_mtime * 1000),
                })

            await session.websocket.send(json.dumps({
                "type": "file_list",
                "path": path or ".",
                "files": files,
            }))
        except PermissionError:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Permission denied: {path}",
            }))
        except Exception as e:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Failed to list files: {e}",
            }))

    async def _handle_create_directory(self, session: Session, path: str):
        """Create a new directory."""
        if not path:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Path is required",
            }))
            return

        target = self._resolve_safe_path(session, path)

        if not target:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Invalid path: outside working directory",
            }))
            return

        if target.exists():
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Path already exists: {path}",
            }))
            return

        try:
            target.mkdir(parents=True, exist_ok=False)
            await session.websocket.send(json.dumps({
                "type": "directory_created",
                "path": path,
            }))
        except PermissionError:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Permission denied: {path}",
            }))
        except Exception as e:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Failed to create directory: {e}",
            }))

    async def _handle_read_file(self, session: Session, path: str):
        """Read file contents."""
        if not path:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Path is required",
            }))
            return

        target = self._resolve_safe_path(session, path)

        if not target:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Invalid path: outside working directory",
            }))
            return

        if not target.exists():
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"File not found: {path}",
            }))
            return

        if not target.is_file():
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Not a file: {path}",
            }))
            return

        # Limit file size to 1MB for reading
        MAX_READ_SIZE = 1024 * 1024
        if target.stat().st_size > MAX_READ_SIZE:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"File too large (max {MAX_READ_SIZE // 1024}KB)",
            }))
            return

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            await session.websocket.send(json.dumps({
                "type": "file_content",
                "path": path,
                "content": content,
                "size": len(content),
            }))
        except PermissionError:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Permission denied: {path}",
            }))
        except Exception as e:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Failed to read file: {e}",
            }))

    async def _handle_delete_file(self, session: Session, path: str):
        """Delete a file or empty directory."""
        if not path:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Path is required",
            }))
            return

        target = self._resolve_safe_path(session, path)

        if not target:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Invalid path: outside working directory",
            }))
            return

        if not target.exists():
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Path not found: {path}",
            }))
            return

        # Don't allow deleting the working directory itself
        if target.resolve() == session.working_dir.resolve():
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": "Cannot delete working directory",
            }))
            return

        try:
            if target.is_file():
                target.unlink()
            elif target.is_dir():
                # Only delete empty directories for safety
                if any(target.iterdir()):
                    await session.websocket.send(json.dumps({
                        "type": "error",
                        "message": "Directory not empty",
                    }))
                    return
                target.rmdir()

            await session.websocket.send(json.dumps({
                "type": "file_deleted",
                "path": path,
            }))
        except PermissionError:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Permission denied: {path}",
            }))
        except Exception as e:
            await session.websocket.send(json.dumps({
                "type": "error",
                "message": f"Failed to delete: {e}",
            }))

    async def _destroy_session(self, session: Session):
        """Cleanup a session."""
        if session.process:
            try:
                session.process.stdin.close() if session.process.stdin else None
                session.process.terminate()
                session.process.wait(timeout=3)
            except Exception:
                session.process.kill()

        self.sessions.pop(session.id, None)

    def _verify_token(self, provided: str) -> bool:
        """Timing-safe token verification (legacy method)."""
        import hmac
        expected = self.config.token
        return hmac.compare_digest(provided, expected)

    def _verify_token_with_manager(self, token: str) -> Tuple[bool, str]:
        """Verify token using TokenManager if available, with fallback.

        Returns:
            Tuple of (valid, status) where status is:
            - "current": Token is the current valid token
            - "grace_period": Token was rotated but still in grace period
            - "valid": Token matches (legacy/fallback mode)
            - "invalid": Token doesn't match
            - "token_expired": Token has expired
        """
        # Use TokenManager if available
        if self._token_manager:
            return self._token_manager.verify_token(token)

        # Fallback to simple timing-safe comparison
        if self._verify_token(token):
            return True, "valid"
        return False, "invalid"
