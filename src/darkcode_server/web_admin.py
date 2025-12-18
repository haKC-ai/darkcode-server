"""Simple web admin dashboard for DarkCode Server.

Security considerations:
- Uses a 6-digit PIN generated at startup (shown in terminal)
- PIN is separate from WebSocket auth token for easier web access
- Served on the same port (HTTP upgrade for WebSocket, regular HTTP for admin)
- All admin actions require PIN authentication
- Read-only by default, write actions require explicit confirmation
"""

import base64
import html
import json
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional
from http import HTTPStatus

# Embedded logo (120x120 DarkCode logo)
LOGO_B64 = "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"

# Embedded favicon (32x32)
FAVICON_B64 = "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"

# HTML template for the admin dashboard
# NOTE: CSS curly braces are escaped ({{ and }}) to avoid Python .format() conflicts
ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DarkCode Server Admin</title>
    <link rel="icon" type="image/png" href="/favicon.ico">
    <style>
        :root {{
            --bg: #0a0a0f;
            --bg-card: #12121a;
            --border: #2a2a3a;
            --text: #e0e0e0;
            --text-dim: #888;
            --accent: #00d4ff;
            --accent-dim: #0088aa;
            --success: #00ff88;
            --warning: #ffaa00;
            --danger: #ff4466;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: 'SF Mono', 'Fira Code', monospace;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{ max-width: 1200px; margin: 0 auto; }}

        header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 30px;
        }}

        .logo {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 24px;
            font-weight: bold;
            color: var(--accent);
        }}

        .logo img {{
            height: 40px;
            width: auto;
        }}

        .logo span {{ color: var(--text-dim); font-weight: normal; }}

        .status-badge {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: rgba(0, 255, 136, 0.1);
            border: 1px solid var(--success);
            border-radius: 20px;
            font-size: 14px;
        }}

        .status-badge::before {{
            content: '';
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}

        .card h2 {{
            font-size: 14px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 15px;
            letter-spacing: 1px;
        }}

        .stat {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
        }}

        .stat:last-child {{ border-bottom: none; }}

        .stat-label {{ color: var(--text-dim); }}
        .stat-value {{ color: var(--accent); font-weight: bold; }}

        .sessions-list {{
            max-height: 300px;
            overflow-y: auto;
        }}

        .session-item {{
            padding: 12px;
            background: rgba(0, 212, 255, 0.05);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 10px;
        }}

        .session-item:last-child {{ margin-bottom: 0; }}

        .session-id {{
            font-size: 12px;
            color: var(--text-dim);
            margin-bottom: 5px;
        }}

        .session-info {{
            display: flex;
            justify-content: space-between;
            font-size: 13px;
        }}

        .empty {{ color: var(--text-dim); font-style: italic; }}

        .qr-section {{
            text-align: center;
            padding: 20px;
        }}

        .qr-section img {{
            max-width: 200px;
            background: white;
            padding: 10px;
            border-radius: 8px;
        }}

        .token-display {{
            font-family: monospace;
            background: rgba(0, 0, 0, 0.5);
            padding: 15px;
            border-radius: 8px;
            word-break: break-all;
            color: var(--warning);
        }}

        .actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }}

        .btn {{
            padding: 10px 20px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: transparent;
            color: var(--text);
            font-family: inherit;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .btn:hover {{
            background: rgba(255, 255, 255, 0.05);
            border-color: var(--accent);
        }}

        .btn-danger {{ border-color: var(--danger); color: var(--danger); }}
        .btn-danger:hover {{ background: rgba(255, 68, 102, 0.1); }}

        .refresh-note {{
            text-align: center;
            color: var(--text-dim);
            font-size: 12px;
            margin-top: 30px;
        }}

        .login-form {{
            max-width: 400px;
            margin: 100px auto;
        }}

        .login-form input {{
            width: 100%;
            padding: 15px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-family: inherit;
            font-size: 24px;
            margin-bottom: 15px;
            text-align: center;
            letter-spacing: 8px;
        }}

        .login-form input:focus {{
            outline: none;
            border-color: var(--accent);
        }}

        .login-form button {{
            width: 100%;
            padding: 15px;
            background: var(--accent);
            border: none;
            border-radius: 8px;
            color: var(--bg);
            font-family: inherit;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }}

        .error {{
            background: rgba(255, 68, 102, 0.1);
            border: 1px solid var(--danger);
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            color: var(--danger);
        }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
    <script>
        // Auto-refresh every 5 seconds
        setTimeout(() => location.reload(), 5000);
    </script>
</body>
</html>
"""

LOGIN_CONTENT = """
<div class="login-form">
    <div style="text-align: center; margin-bottom: 30px;">
        <img src="data:image/png;base64,{logo_b64}" alt="DarkCode" style="height: 80px; margin-bottom: 15px;">
        <h1 style="color: var(--accent);">Admin Login</h1>
    </div>
    {error}
    <form id="loginForm" onsubmit="return handleLogin(event)">
        <input type="text" id="pinInput" name="pin" placeholder="000000" maxlength="6" pattern="[0-9]{{6}}" autofocus inputmode="numeric">
        <button type="submit">Login</button>
    </form>
    <p style="text-align: center; margin-top: 20px; color: var(--text-dim); font-size: 12px;">
        Enter the 6-digit PIN shown in the terminal
    </p>
</div>
<script>
function handleLogin(e) {{
    e.preventDefault();
    const pin = document.getElementById('pinInput').value;
    if (pin && pin.length === 6) {{
        window.location.href = '/admin/login?pin=' + encodeURIComponent(pin);
    }}
    return false;
}}
// Auto-focus and select
document.getElementById('pinInput').focus();
</script>
"""

DASHBOARD_CONTENT = """
<header>
    <div class="logo">
        <img src="data:image/png;base64,{logo_b64}" alt="DarkCode">
        DARKCODE <span>admin</span>
    </div>
    <div class="status-badge">Server Running</div>
</header>

<div class="grid">
    <div class="card">
        <h2>Server Status</h2>
        <div class="stat">
            <span class="stat-label">Uptime</span>
            <span class="stat-value">{uptime}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Port</span>
            <span class="stat-value">{port}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Working Directory</span>
            <span class="stat-value" title="{working_dir}">{working_dir_short}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Server State</span>
            <span class="stat-value">{state}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Device Lock</span>
            <span class="stat-value">{device_lock}</span>
        </div>
        <div class="stat">
            <span class="stat-label">TLS</span>
            <span class="stat-value">{tls_status}</span>
        </div>
    </div>

    <div class="card">
        <h2>Active Sessions ({session_count})</h2>
        <div class="sessions-list">
            {sessions_html}
        </div>
    </div>

    <div class="card">
        <h2>Authentication</h2>
        <p class="stat-label" style="margin-bottom: 10px;">Auth Token (masked)</p>
        <div class="token-display">{token_masked}</div>
        <div class="actions">
            <button class="btn" onclick="copyToken()">Copy Full Token</button>
        </div>
    </div>

    <div class="card">
        <h2>Connection Info</h2>
        <div class="stat">
            <span class="stat-label">Local IP</span>
            <span class="stat-value">{local_ip}</span>
        </div>
        {tailscale_row}
        <div class="stat">
            <span class="stat-label">WebSocket URL</span>
            <span class="stat-value">{ws_url}</span>
        </div>
    </div>
</div>

<p class="refresh-note">Auto-refreshing every 5 seconds | <a href="/admin/logout" style="color: var(--accent);">Logout</a></p>

<script>
    const TOKEN = '{token_full}';
    function copyToken() {{
        navigator.clipboard.writeText(TOKEN).then(() => {{
            alert('Token copied to clipboard');
        }});
    }}
</script>
"""


def generate_web_pin() -> str:
    """Generate a 6-digit PIN for web admin login."""
    return ''.join(str(secrets.randbelow(10)) for _ in range(6))


class WebAdminHandler:
    """Handle HTTP requests for the web admin dashboard."""

    # Class-level PIN that persists across handler instances
    _web_pin: Optional[str] = None

    def __init__(self, config, server_instance=None):
        self.config = config
        self.server = server_instance
        self.start_time = time.time()
        self._authenticated_sessions = set()  # Store authenticated session cookies

        # Generate PIN once on first handler creation
        if WebAdminHandler._web_pin is None:
            WebAdminHandler._web_pin = generate_web_pin()

    @classmethod
    def get_web_pin(cls) -> str:
        """Get the current web PIN, generating one if needed."""
        if cls._web_pin is None:
            cls._web_pin = generate_web_pin()
        return cls._web_pin

    @classmethod
    def regenerate_pin(cls) -> str:
        """Regenerate the web PIN."""
        cls._web_pin = generate_web_pin()
        return cls._web_pin

    def _generate_session_cookie(self) -> str:
        """Generate a random session cookie."""
        return secrets.token_urlsafe(32)

    def _is_authenticated(self, cookies: dict) -> bool:
        """Check if the request has a valid session cookie."""
        session_id = cookies.get('darkcode_admin_session')
        return session_id in self._authenticated_sessions

    def _verify_pin(self, pin: str) -> bool:
        """Verify the provided PIN matches the web PIN."""
        import hmac
        if WebAdminHandler._web_pin is None:
            return False
        return hmac.compare_digest(pin.strip(), WebAdminHandler._web_pin)

    def _parse_cookies(self, cookie_header: str) -> dict:
        """Parse cookies from header."""
        cookies = {}
        if cookie_header:
            for item in cookie_header.split(';'):
                if '=' in item:
                    key, value = item.strip().split('=', 1)
                    cookies[key] = value
        return cookies

    def _parse_form_data(self, body: bytes) -> dict:
        """Parse URL-encoded form data."""
        from urllib.parse import parse_qs
        data = parse_qs(body.decode('utf-8'))
        return {k: v[0] if len(v) == 1 else v for k, v in data.items()}

    def handle_request(self, path: str, method: str, headers: dict, body: bytes = b'') -> tuple:
        """Handle an HTTP request and return (status, headers, body).

        Returns:
            Tuple of (status_code, response_headers_dict, response_body_bytes)
        """
        from urllib.parse import urlparse, parse_qs

        cookies = self._parse_cookies(headers.get('Cookie', ''))

        # Parse path and query string
        parsed = urlparse(path)
        clean_path = parsed.path
        query_params = parse_qs(parsed.query)

        # Route requests
        if clean_path == '/admin' or clean_path == '/admin/':
            if self._is_authenticated(cookies):
                return self._dashboard_page()
            else:
                return self._login_page()

        elif clean_path == '/admin/logo':
            # Serve embedded logo
            return self._serve_logo()

        elif clean_path == '/admin/login':
            # Handle login - check for PIN in query params
            pin = ''
            if 'pin' in query_params:
                pin = query_params['pin'][0]
            elif body:
                form_data = self._parse_form_data(body)
                pin = form_data.get('pin', '')

            if pin:
                if self._verify_pin(pin):
                    session_cookie = self._generate_session_cookie()
                    self._authenticated_sessions.add(session_cookie)
                    return (
                        302,
                        {
                            'Location': '/admin',
                            'Set-Cookie': f'darkcode_admin_session={session_cookie}; HttpOnly; SameSite=Strict; Path=/admin'
                        },
                        b''
                    )
                else:
                    return self._login_page(error="Invalid PIN")
            else:
                # Show login page
                return self._login_page()

        elif clean_path == '/admin/logout':
            session_id = cookies.get('darkcode_admin_session')
            if session_id:
                self._authenticated_sessions.discard(session_id)
            return (
                302,
                {
                    'Location': '/admin',
                    'Set-Cookie': 'darkcode_admin_session=; HttpOnly; SameSite=Strict; Path=/admin; Max-Age=0'
                },
                b''
            )

        elif clean_path == '/admin/api/status':
            if not self._is_authenticated(cookies):
                return (401, {'Content-Type': 'application/json'}, b'{"error": "Unauthorized"}')
            return self._api_status()

        else:
            return (404, {'Content-Type': 'text/html'}, b'Not Found')

    def _serve_logo(self) -> tuple:
        """Serve the embedded DarkCode logo."""
        logo_data = base64.b64decode(LOGO_B64)
        return (200, {'Content-Type': 'image/png', 'Cache-Control': 'max-age=3600'}, logo_data)

    def _login_page(self, error: str = '') -> tuple:
        """Render the login page."""
        error_html = f'<div class="error">{html.escape(error)}</div>' if error else ''
        content = LOGIN_CONTENT.format(error=error_html, logo_b64=LOGO_B64)
        page = ADMIN_HTML.format(content=content)
        return (200, {'Content-Type': 'text/html'}, page.encode('utf-8'))

    def _dashboard_page(self) -> tuple:
        """Render the main dashboard."""
        # Calculate uptime
        uptime_secs = int(time.time() - self.start_time)
        uptime = str(timedelta(seconds=uptime_secs))

        # Get session info
        sessions_html = '<p class="empty">No active sessions</p>'
        session_count = 0
        if self.server and hasattr(self.server, 'sessions'):
            session_count = len(self.server.sessions)
            if session_count > 0:
                sessions_html = ''
                for sid, session in self.server.sessions.items():
                    guest_badge = ' <span style="color: var(--warning);">[guest]</span>' if getattr(session, 'is_guest', False) else ''
                    sessions_html += f'''
                    <div class="session-item">
                        <div class="session-id">ID: {sid[:8]}...{guest_badge}</div>
                        <div class="session-info">
                            <span>IP: {getattr(session, 'client_ip', 'unknown')}</span>
                            <span>Msgs: {getattr(session, 'message_count', 0)}</span>
                        </div>
                    </div>
                    '''

        # Get server state
        state = 'running'
        if self.server and hasattr(self.server, 'state'):
            state = self.server.state.value

        # Get IPs
        local_ips = self.config.get_local_ips()
        local_ip = local_ips[0]['address'] if local_ips else '127.0.0.1'

        tailscale_ip = self.config.get_tailscale_ip()
        tailscale_row = ''
        if tailscale_ip:
            tailscale_row = f'''
            <div class="stat">
                <span class="stat-label">Tailscale IP</span>
                <span class="stat-value" style="color: var(--success);">{tailscale_ip}</span>
            </div>
            '''

        # Working dir (shortened)
        working_dir = str(self.config.working_dir)
        working_dir_short = working_dir if len(working_dir) <= 30 else '...' + working_dir[-27:]

        # WebSocket URL
        protocol = 'wss' if self.config.tls_enabled else 'ws'
        ws_url = f'{protocol}://{local_ip}:{self.config.port}'

        content = DASHBOARD_CONTENT.format(
            logo_b64=LOGO_B64,
            uptime=uptime,
            port=self.config.port,
            working_dir=working_dir,
            working_dir_short=working_dir_short,
            state=state,
            device_lock='Enabled' if self.config.device_lock else 'Disabled',
            tls_status='Enabled (wss://)' if self.config.tls_enabled else 'Disabled (ws://)',
            session_count=session_count,
            sessions_html=sessions_html,
            token_masked=self.config.token[:4] + '*' * 20 + self.config.token[-4:],
            token_full=self.config.token,
            local_ip=local_ip,
            tailscale_row=tailscale_row,
            ws_url=ws_url,
        )

        page = ADMIN_HTML.format(content=content)
        return (200, {'Content-Type': 'text/html'}, page.encode('utf-8'))

    def _api_status(self) -> tuple:
        """Return status as JSON for API consumers."""
        uptime_secs = int(time.time() - self.start_time)
        session_count = 0
        if self.server and hasattr(self.server, 'sessions'):
            session_count = len(self.server.sessions)

        data = {
            'uptime_seconds': uptime_secs,
            'port': self.config.port,
            'session_count': session_count,
            'state': self.server.state.value if self.server and hasattr(self.server, 'state') else 'unknown',
            'device_lock': self.config.device_lock,
            'tls_enabled': self.config.tls_enabled,
        }

        return (200, {'Content-Type': 'application/json'}, json.dumps(data).encode('utf-8'))


def serve_favicon() -> tuple:
    """Serve the embedded favicon."""
    favicon_data = base64.b64decode(FAVICON_B64)
    return (200, {'Content-Type': 'image/png', 'Cache-Control': 'max-age=86400'}, favicon_data)
