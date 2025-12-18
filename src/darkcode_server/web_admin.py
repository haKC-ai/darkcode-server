"""Simple web admin dashboard for DarkCode Server.

Security considerations:
- Uses the same auth token as WebSocket connections
- Served on the same port (HTTP upgrade for WebSocket, regular HTTP for admin)
- All admin actions require token authentication
- Read-only by default, write actions require explicit confirmation
"""

import base64
import html
import json
import time
from datetime import datetime, timedelta
from typing import Optional
from http import HTTPStatus

# HTML template for the admin dashboard
ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DarkCode Server Admin</title>
    <style>
        :root {
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
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'SF Mono', 'Fira Code', monospace;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
        }

        .container { max-width: 1200px; margin: 0 auto; }

        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 30px;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 24px;
            font-weight: bold;
            color: var(--accent);
        }

        .logo img {
            height: 40px;
            width: auto;
        }

        .logo span { color: var(--text-dim); font-weight: normal; }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: rgba(0, 255, 136, 0.1);
            border: 1px solid var(--success);
            border-radius: 20px;
            font-size: 14px;
        }

        .status-badge::before {
            content: '';
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }

        .card h2 {
            font-size: 14px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 15px;
            letter-spacing: 1px;
        }

        .stat {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid var(--border);
        }

        .stat:last-child { border-bottom: none; }

        .stat-label { color: var(--text-dim); }
        .stat-value { color: var(--accent); font-weight: bold; }

        .sessions-list {
            max-height: 300px;
            overflow-y: auto;
        }

        .session-item {
            padding: 12px;
            background: rgba(0, 212, 255, 0.05);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .session-item:last-child { margin-bottom: 0; }

        .session-id {
            font-size: 12px;
            color: var(--text-dim);
            margin-bottom: 5px;
        }

        .session-info {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
        }

        .empty { color: var(--text-dim); font-style: italic; }

        .qr-section {
            text-align: center;
            padding: 20px;
        }

        .qr-section img {
            max-width: 200px;
            background: white;
            padding: 10px;
            border-radius: 8px;
        }

        .token-display {
            font-family: monospace;
            background: rgba(0, 0, 0, 0.5);
            padding: 15px;
            border-radius: 8px;
            word-break: break-all;
            color: var(--warning);
        }

        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }

        .btn {
            padding: 10px 20px;
            border: 1px solid var(--border);
            border-radius: 8px;
            background: transparent;
            color: var(--text);
            font-family: inherit;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn:hover {
            background: rgba(255, 255, 255, 0.05);
            border-color: var(--accent);
        }

        .btn-danger { border-color: var(--danger); color: var(--danger); }
        .btn-danger:hover { background: rgba(255, 68, 102, 0.1); }

        .refresh-note {
            text-align: center;
            color: var(--text-dim);
            font-size: 12px;
            margin-top: 30px;
        }

        .login-form {
            max-width: 400px;
            margin: 100px auto;
        }

        .login-form input {
            width: 100%;
            padding: 15px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-family: inherit;
            font-size: 16px;
            margin-bottom: 15px;
        }

        .login-form input:focus {
            outline: none;
            border-color: var(--accent);
        }

        .login-form button {
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
        }

        .error {
            background: rgba(255, 68, 102, 0.1);
            border: 1px solid var(--danger);
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            color: var(--danger);
        }
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
        <img src="/admin/logo" alt="DarkCode" style="height: 60px; margin-bottom: 15px;">
        <h1 style="color: var(--accent);">Admin Login</h1>
    </div>
    {error}
    <form id="loginForm" onsubmit="return handleLogin(event)">
        <input type="password" id="tokenInput" name="token" placeholder="Enter auth token" autofocus>
        <button type="submit">Login</button>
    </form>
    <p style="text-align: center; margin-top: 20px; color: var(--text-dim); font-size: 12px;">
        Use the same token shown when starting the server
    </p>
</div>
<script>
function handleLogin(e) {{
    e.preventDefault();
    const token = document.getElementById('tokenInput').value;
    if (token) {{
        // Redirect with token in URL (secure over HTTPS, temporary in URL)
        window.location.href = '/admin/login?token=' + encodeURIComponent(token);
    }}
    return false;
}}
</script>
"""

DASHBOARD_CONTENT = """
<header>
    <div class="logo">
        <img src="/admin/logo" alt="DarkCode">
        DARKCODE <span>admin</span>
    </div>
    <div class="status-badge">Server Running</div>
</header>

<div class="grid">
    <div class="card">
        <h2>📊 Server Status</h2>
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
        <h2>👥 Active Sessions ({session_count})</h2>
        <div class="sessions-list">
            {sessions_html}
        </div>
    </div>

    <div class="card">
        <h2>🔑 Authentication</h2>
        <p class="stat-label" style="margin-bottom: 10px;">Auth Token (masked)</p>
        <div class="token-display">{token_masked}</div>
        <div class="actions">
            <button class="btn" onclick="copyToken()">📋 Copy Full Token</button>
        </div>
    </div>

    <div class="card">
        <h2>🌐 Connection Info</h2>
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

<p class="refresh-note">Auto-refreshing every 5 seconds • <a href="/admin/logout" style="color: var(--accent);">Logout</a></p>

<script>
    const TOKEN = '{token_full}';
    function copyToken() {{
        navigator.clipboard.writeText(TOKEN).then(() => {{
            alert('Token copied to clipboard');
        }});
    }}
</script>
"""


class WebAdminHandler:
    """Handle HTTP requests for the web admin dashboard."""

    def __init__(self, config, server_instance=None):
        self.config = config
        self.server = server_instance
        self.start_time = time.time()
        self._authenticated_sessions = set()  # Store authenticated session cookies

    def _generate_session_cookie(self) -> str:
        """Generate a random session cookie."""
        import secrets
        return secrets.token_urlsafe(32)

    def _is_authenticated(self, cookies: dict) -> bool:
        """Check if the request has a valid session cookie."""
        session_id = cookies.get('darkcode_admin_session')
        return session_id in self._authenticated_sessions

    def _verify_token(self, token: str) -> bool:
        """Verify the provided token matches the server token."""
        import hmac
        return hmac.compare_digest(token.strip(), self.config.token)

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
            # Serve the logo
            return self._serve_logo()

        elif clean_path == '/admin/login':
            # Handle login - check for token in query params (workaround for POST limitation)
            token = ''
            if 'token' in query_params:
                token = query_params['token'][0]
            elif body:
                form_data = self._parse_form_data(body)
                token = form_data.get('token', '')

            if token:
                if self._verify_token(token):
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
                    return self._login_page(error="Invalid token")
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
        """Serve the DarkCode logo."""
        from pathlib import Path

        # Try to find the logo
        logo_paths = [
            Path(__file__).parent / "assets" / "darkcode_logo.png",
            Path(__file__).parent.parent.parent / "assets" / "darkcode_logo.png",
        ]

        for logo_path in logo_paths:
            if logo_path.exists():
                logo_data = logo_path.read_bytes()
                return (200, {'Content-Type': 'image/png', 'Cache-Control': 'max-age=3600'}, logo_data)

        # Return a simple SVG fallback
        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
            <rect fill="#0a0a0f" width="100" height="100" rx="10"/>
            <text x="50" y="60" text-anchor="middle" fill="#00d4ff" font-size="40" font-family="monospace">DC</text>
        </svg>'''
        return (200, {'Content-Type': 'image/svg+xml'}, svg)

    def _login_page(self, error: str = '') -> tuple:
        """Render the login page."""
        error_html = f'<div class="error">{html.escape(error)}</div>' if error else ''
        content = LOGIN_CONTENT.format(error=error_html)
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
