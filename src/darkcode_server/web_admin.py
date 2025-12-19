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

from darkcode_server.qrcode import generate_qr_png_base64

# ASCII art logo with synthwave gradient styling
ASCII_LOGO = r"""
░▒▓███████▓▒░ ░▒▓██████▓▒░░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░▒▓███████▓▒░░▒▓███████▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░
░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░
   __ _________  ________  ________  ___________ __
  / / \_   ___ \ \_____  \ \______ \ \_   _____/ \ \
 / /  /    \  \/  /   |   \ |    |  \ |    __)_   \ \
 \ \  \     \____/    |    \|    `   \|        \  / /
  \_\  \______  /\_______  /_______  /_______  / /_/
              \/         \/        \/ SERVER \/
"""

# Embedded favicon (32x32)
FAVICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAAXNSR0IArs4c6QAAAERlWElmTU0AKgAAAAgAAYdpAAQAAAABAAAAGgAAAAAAA6ABAAMAAAABAAEAAKACAAQAAAABAAAAIKADAAQAAAABAAAAIAAAAACshmLzAAAGO0lEQVRYCe1VbWwcRxl+dnb28/Y2vnOcs3txXcet3QapLWlpAxJIELU/EG1UtUpVIYgAoQqRP0QCUVGIFSkSqviBhCANiFAqARIF8SMIkNJKVVolaZt+2InTJE3i1vFdz3buy/azt7e7M7y7yQWXOu2P/oAfntPczM7OzvPMM8/7DrBW1hRYU+B/rIDSw5+c/LN+y4Z7U0C9N3Stta207D20vYaCdYDj6OH27T9uS/mciN/FC12dpCgKkrHeNx/VJgRmZhado3/0DxXPiQndUGGZOizLoMphOYxzTZUKExHXCIjFQAqYjqDUWKgee6kWjo3nEEUMA0MaIkfDbffyqS0T/g9c1y1/FHj8jsd/nqekucbv8lsibTATXDdhwISjMwincdLNymzGsvJ+cJUAbTWkvusO32jf5+CVV1oYHMpiuabC1VVcnOV3dVTceb7U2HnzYPpUjHG9QvsB7VRKVWWRpivQCFSnqhkKbAcwU8rLxeidbUG6NZ0bJdANRMIAqssRzr4dIKi72Pq5FErlEqqNJooLHqrFJs7NqlveLGrPv77UeeB64PF4okCl4vlBxIvMjrgwPESGgLQChCZHAL/xtW/dcXbfvuP3f/bW8YP1RWvb/CUvCkNFgikIGxJal2HL1hSOv7YkNbiyWuSwZRvvB2q6Av13hxeau+/LOc+uRiTxgJRSeXrvu/dHvpKXMpKqxsC5ojjrDOkMKS8+uGNw9srHk/x73/3yxPjIDZ+xVZ1JDqkyFZGISC1NOplITM9dFlNzy3Dz5Of1KvpyOtMNpfvpzQNvP7T/ZyeVyckPGDQhcPhQ8cbKjPlmeVZ1UykNhqFL02RKX4bs3O/94ktftXevZP+3A/W9rOE8EbQYIxGEqpKUFqSRhqIP+fLQW+dwsREivyUPs09AM8FMm+POMfcvI8z7zu19fdXeeokHaAe6hLS7vuRhCE4b0qJQ4ZdL4Ivz3XRvcq996PF1P6nJyi4vCrxGA7zeBK81oVVa1FYN7Stf2KzdvjGlld6a15jPKIbIYWSzN2bbj16Q9r+OLvu39tZKCGgaHQJFl5ACcY0lXVwKUKnQYMg+IFnvw53fHzgQZIoPBjxo1tsC1Y5AxZe43JG4VFax9fPjGLvJxekjc0hxHfVaiD5L4tjJ2j1liReON5u5eK2EQNyJKUSCwCOBpXIXtTqZMKRwo+fVyokTRTtqu49Ua5FZ73SIQBfldoAlkn7JEzhxfhkzUxVkMi4qJR+uwVGjTW3MGrIbit+kU6nkGJIo6BEQRGK52aWqQOccXSIQRR+G/8df5zce+Tt7plpg23yvAUlhKztUKUsZ5KFmcQFTR87ghpuHYVEsU3SjXZfIj5itwX5118P91jO9VRMCPj3FCviEuExyMkWjXEchRuiCVFlZ/vD79++ZekM+u1jAhO9XKTOqECGB+yrMrI7C4iW889p7GN08DtM0YXNG4Ao2fcosZB2x8+Eh54WV6/1HAUqw9aYPrythEeUwjnEisPIEDv6y8OjFGbF/aUFk/LANGYdA/JMMZobh0twZlM6WMXrLBDTahMkpRDscI5v4tCWDxx4b6z+9EjzuJwQMkkBEUi63fDCKqTAKSYWrBCIRkjjKr38+/+TceeypVAI1lCGBS4SCYkelrJkFLpw5hVahg3z+JjIOLUykGKWloSH2TxZWv/HNrZsW/hv8GoG4Q6kQHUr2JqXZkEWIr7Ru0AXjyvqnnyocWCjwb9fqbcrDV46ESFFwq5CpEKdPTIM1OHL9ecjYM6EKQ9exPif3d4Lp3T/c/sVOjLFauXIEBNrpUF4n22sayUbSM/JAN/DR7do7RIuuJtNHzk4jIkNFdFw+Sb/YKuPU0WlYgQM3lUlIx95x0szrGwgn9+wafmo10JVjCQFdGNLvNhJgERtP4VjXn8LASFAyMuVfSUOctTVdChEpEWU9UKUkFLx66GRDem0xkB8i/5SRsvvp9vKQHTRL+57c9KHzXgnc618zYUi7D+kYjD4Dw6OanxttHzQ2XP7p1x+/e643+XrtqzPXe/Px4wmBVpWuMwE7P5zC2GYczo529uzcdduxj//8k89ICJy7UFjUrfRvJ+5WXszt/dGfdijPrZJ+PjnY2gprCvxfKvBvatvRlM14v0kAAAAASUVORK5CYII="

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

        .ascii-logo {{
            font-family: 'Courier New', monospace;
            font-size: 6px;
            line-height: 1.1;
            white-space: pre;
            background: linear-gradient(90deg, #ff00ff 0%, #00ffff 25%, #ff00ff 50%, #00ffff 75%, #ff00ff 100%);
            background-size: 200% 100%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: synthwave 3s linear infinite;
            font-size: 10px;
            line-height: 1.1;
        }}

        @keyframes synthwave {{
            0% {{ background-position: 0% 50%; }}
            100% {{ background-position: 200% 50%; }}
        }}

        .ascii-logo-container {{
            text-align: center;
            padding: 10px 0 20px 0;
            margin-bottom: 20px;
        }}

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

        .success {{
            background: rgba(0, 255, 136, 0.1);
            border: 1px solid var(--success);
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            color: var(--success);
        }}

        .nav-links {{
            display: flex;
            gap: 20px;
        }}

        .nav-link {{
            color: var(--text-dim);
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 8px;
            transition: all 0.2s;
        }}

        .nav-link:hover {{
            color: var(--text);
            background: rgba(255, 255, 255, 0.05);
        }}

        .nav-link.active {{
            color: var(--accent);
            background: rgba(0, 212, 255, 0.1);
        }}

        .form-group {{
            margin-bottom: 20px;
        }}

        .form-group label {{
            display: block;
            color: var(--text-dim);
            margin-bottom: 8px;
            font-size: 13px;
        }}

        .form-group input, .form-group select {{
            width: 100%;
            padding: 12px;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-family: inherit;
            font-size: 14px;
        }}

        .form-group input:focus, .form-group select:focus {{
            outline: none;
            border-color: var(--accent);
        }}

        .form-group .hint {{
            font-size: 11px;
            color: var(--text-dim);
            margin-top: 5px;
        }}

        .toggle-switch {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .toggle-switch input[type="checkbox"] {{
            width: 50px;
            height: 26px;
            appearance: none;
            background: var(--border);
            border-radius: 13px;
            position: relative;
            cursor: pointer;
            transition: all 0.3s;
        }}

        .toggle-switch input[type="checkbox"]::after {{
            content: '';
            position: absolute;
            width: 22px;
            height: 22px;
            background: var(--text);
            border-radius: 50%;
            top: 2px;
            left: 2px;
            transition: all 0.3s;
        }}

        .toggle-switch input[type="checkbox"]:checked {{
            background: var(--accent);
        }}

        .toggle-switch input[type="checkbox"]:checked::after {{
            left: 26px;
        }}

        .form-actions {{
            display: flex;
            gap: 10px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
        }}

        .btn-primary {{
            background: var(--accent);
            color: var(--bg);
            border: none;
            font-weight: bold;
        }}

        .btn-primary:hover {{
            background: var(--accent-dim);
        }}

        .section-title {{
            font-size: 16px;
            color: var(--accent);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--border);
        }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""

LOGIN_CONTENT = """
<div class="login-form">
    <div class="ascii-logo-container" style="margin-bottom: 20px;">
        <pre class="ascii-logo">{ascii_logo}</pre>
    </div>
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: var(--accent);">Admin Login</h1>
    </div>
    {error}
    <form id="loginForm" method="GET" action="/admin/login">
        <input type="text" id="pinInput" name="pin" placeholder="000000" maxlength="6" pattern="[0-9]{{6}}" autofocus autocomplete="off">
        <button type="submit">Login</button>
    </form>
    <p style="text-align: center; margin-top: 20px; color: var(--text-dim); font-size: 12px;">
        Enter the 6-digit PIN shown in the terminal
    </p>
</div>
<script>
// Auto-focus
document.getElementById('pinInput').focus();
</script>
"""

DASHBOARD_CONTENT = """
<div class="ascii-logo-container">
    <pre class="ascii-logo">{ascii_logo}</pre>
</div>

<header>
    <div class="logo">
        DARKCODE <span>admin</span>
    </div>
    <div class="status-badge">Server Running</div>
</header>

{message}
<div id="save-status" style="display: none; position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; z-index: 1000;"></div>

<div class="grid">
    <div class="card">
        <h2>Quick Connect</h2>
        <div style="text-align: center; margin-bottom: 15px;">
            <div style="background: white; padding: 10px; border-radius: 8px; display: inline-block;">
                <img src="data:image/png;base64,{qr_code_base64}" alt="Connection QR Code" style="max-width: 180px;">
            </div>
            <p class="stat-label" style="margin-top: 10px;">Scan with DarkCode app</p>
        </div>
        <p class="stat-label" style="margin-bottom: 10px;">Auth Token (masked)</p>
        <div class="token-display">{token_masked}</div>
        <div class="actions" style="margin-top: 15px;">
            <button class="btn" onclick="copyToken()">Copy Full Token</button>
            <button class="btn btn-danger" onclick="if(confirm('Generate new token? Current connections will be invalidated.')) location.href='/admin/config/rotate-token?session={session_token}'">
                Rotate Token
            </button>
            {unbind_button}
        </div>
    </div>

    <div class="card">
        <h2>Server Status</h2>
        <div class="stat">
            <span class="stat-label">Mode</span>
            <span class="stat-value" style="color: {daemon_mode_color};">{daemon_mode}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Uptime</span>
            <span class="stat-value">{uptime}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Local IP</span>
            <span class="stat-value">{local_ip}</span>
        </div>
        {tailscale_row}
        <div class="stat">
            <span class="stat-label">WebSocket URL</span>
            <span class="stat-value">{ws_url}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Server State</span>
            <span class="stat-value">{state}</span>
        </div>
        <div class="stat">
            <span class="stat-label">Active Sessions</span>
            <span class="stat-value">{session_count}</span>
        </div>
        <div class="sessions-list" style="margin-top: 10px; max-height: 150px;">
            {sessions_html}
        </div>
    </div>

    <div class="card">
        <h2>Server Settings</h2>
        <div class="form-group">
            <label>Port</label>
            <input type="number" id="port" value="{port}" min="1" max="65535" onchange="saveSetting('port', this.value)">
        </div>
        <div class="form-group">
            <label>Working Directory</label>
            <input type="text" id="working_dir" value="{working_dir}" onchange="saveSetting('working_dir', this.value)">
        </div>
        <div class="form-group">
            <label>Server Name</label>
            <input type="text" id="server_name" value="{server_name}" onchange="saveSetting('server_name', this.value)">
        </div>
        <div class="form-group">
            <label>Permission Mode</label>
            <select id="permission_mode" onchange="saveSetting('permission_mode', this.value)">
                <option value="default" {perm_default}>default</option>
                <option value="acceptEdits" {perm_accept}>acceptEdits</option>
                <option value="bypassPermissions" {perm_bypass}>bypassPermissions</option>
            </select>
        </div>
    </div>

    <div class="card">
        <h2>Security Settings</h2>
        <div class="form-group toggle-switch">
            <input type="checkbox" id="device_lock" {device_lock_checked} onchange="saveSetting('device_lock', this.checked ? '1' : '0')">
            <label for="device_lock">Device Lock</label>
        </div>
        <div class="form-group toggle-switch">
            <input type="checkbox" id="tls_enabled" {tls_enabled_checked} onchange="saveSetting('tls_enabled', this.checked ? '1' : '0')">
            <label for="tls_enabled">TLS Enabled</label>
        </div>
        <div class="form-group">
            <label>Max Sessions/IP</label>
            <input type="number" id="max_sessions_per_ip" value="{max_sessions_per_ip}" min="1" max="100" onchange="saveSetting('max_sessions_per_ip', this.value)">
        </div>
        <div class="form-group">
            <label>Idle Timeout (sec)</label>
            <input type="number" id="idle_timeout" value="{idle_timeout}" min="0" onchange="saveSetting('idle_timeout', this.value)">
        </div>
    </div>

    <div class="card">
        <h2>Logs</h2>
        <div class="log-viewer" id="log-viewer" style="background: #0a0a0f; border: 1px solid var(--border); border-radius: 8px; padding: 10px; font-family: monospace; font-size: 11px; max-height: 200px; overflow-y: auto; white-space: pre-wrap; color: var(--text-dim);">
{log_content}
        </div>
        <div class="actions" style="margin-top: 10px;">
            <button class="btn" onclick="refreshLogs()">Refresh</button>
            <button class="btn" onclick="downloadLogs()">Download</button>
        </div>
    </div>
</div>

<p class="refresh-note"><a href="/admin/logout" style="color: var(--accent);">Logout</a></p>

<script>
    const TOKEN = '{token_full}';
    const SESSION = '{session_token}';

    function copyToken() {{
        navigator.clipboard.writeText(TOKEN).then(() => {{
            alert('Token copied to clipboard');
        }});
    }}

    function saveSetting(key, value) {{
        const status = document.getElementById('save-status');
        status.style.display = 'block';
        status.style.background = 'rgba(0, 212, 255, 0.2)';
        status.style.border = '1px solid var(--accent)';
        status.style.color = 'var(--accent)';
        status.textContent = 'Saving...';

        fetch('/admin/config/set?session=' + SESSION + '&key=' + encodeURIComponent(key) + '&value=' + encodeURIComponent(value))
            .then(r => r.json())
            .then(data => {{
                if (data.success) {{
                    status.style.background = 'rgba(0, 255, 136, 0.2)';
                    status.style.border = '1px solid var(--success)';
                    status.style.color = 'var(--success)';
                    status.textContent = 'Saved!';
                }} else {{
                    status.style.background = 'rgba(255, 68, 102, 0.2)';
                    status.style.border = '1px solid var(--danger)';
                    status.style.color = 'var(--danger)';
                    status.textContent = 'Error: ' + (data.error || 'Unknown');
                }}
                setTimeout(() => status.style.display = 'none', 2000);
            }})
            .catch(err => {{
                status.style.background = 'rgba(255, 68, 102, 0.2)';
                status.style.border = '1px solid var(--danger)';
                status.style.color = 'var(--danger)';
                status.textContent = 'Error saving';
                setTimeout(() => status.style.display = 'none', 2000);
            }});
    }}

    function refreshLogs() {{
        fetch('/admin/logs?session=' + SESSION)
            .then(r => r.text())
            .then(data => {{
                document.getElementById('log-viewer').textContent = data;
                document.getElementById('log-viewer').scrollTop = document.getElementById('log-viewer').scrollHeight;
            }});
    }}

    function downloadLogs() {{
        window.location.href = '/admin/logs/download?session=' + SESSION;
    }}
</script>
"""

CONFIG_CONTENT = """
<header>
    <div class="logo">
        DARKCODE <span>admin</span>
    </div>
    <nav class="nav-links">
        <a href="/admin?session={session_token}" class="nav-link">Dashboard</a>
        <a href="/admin/config?session={session_token}" class="nav-link active">Config</a>
    </nav>
    <div class="status-badge">Server Running</div>
</header>

{message}

<div id="save-status" style="display: none; position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 8px; z-index: 1000;"></div>

<div class="grid">
    <div class="card">
        <h2 class="section-title">Server Settings</h2>

        <div class="form-group">
            <label>Port</label>
            <input type="number" id="port" value="{port}" min="1" max="65535" onchange="saveSetting('port', this.value)">
            <div class="hint">WebSocket server port (default: 3100)</div>
        </div>

        <div class="form-group">
            <label>Working Directory</label>
            <input type="text" id="working_dir" value="{working_dir}" onchange="saveSetting('working_dir', this.value)">
            <div class="hint">Directory where Claude Code operates</div>
        </div>

        <div class="form-group">
            <label>Browse Directory (optional)</label>
            <input type="text" id="browse_dir" value="{browse_dir}" placeholder="Defaults to working directory" onchange="saveSetting('browse_dir', this.value)">
            <div class="hint">Default directory for app file browser</div>
        </div>

        <div class="form-group">
            <label>Server Name</label>
            <input type="text" id="server_name" value="{server_name}" onchange="saveSetting('server_name', this.value)">
            <div class="hint">Display name shown in the app</div>
        </div>

        <div class="form-group">
            <label>Permission Mode</label>
            <select id="permission_mode" onchange="saveSetting('permission_mode', this.value)">
                <option value="default" {perm_default}>default - Ask for all permissions</option>
                <option value="acceptEdits" {perm_accept}>acceptEdits - Auto-accept file edits</option>
                <option value="bypassPermissions" {perm_bypass}>bypassPermissions - Skip all prompts (dangerous)</option>
            </select>
            <div class="hint">How Claude Code handles permission prompts</div>
        </div>
    </div>

    <div class="card">
        <h2 class="section-title">Security Settings</h2>

        <div class="form-group toggle-switch">
            <input type="checkbox" id="device_lock" {device_lock_checked} onchange="saveSetting('device_lock', this.checked ? '1' : '0')">
            <label for="device_lock">Device Lock</label>
        </div>
        <div class="hint" style="margin-bottom: 20px;">Lock server to first authenticated device</div>

        <div class="form-group toggle-switch">
            <input type="checkbox" id="local_only" {local_only_checked} onchange="saveSetting('local_only', this.checked ? '1' : '0')">
            <label for="local_only">Local Only</label>
        </div>
        <div class="hint" style="margin-bottom: 20px;">Only accept connections from localhost (SSH tunnel mode)</div>

        <div class="form-group">
            <label>Max Sessions per IP</label>
            <input type="number" id="max_sessions_per_ip" value="{max_sessions_per_ip}" min="1" max="100" onchange="saveSetting('max_sessions_per_ip', this.value)">
            <div class="hint">Maximum concurrent sessions from one IP</div>
        </div>

        <div class="form-group">
            <label>Idle Timeout (seconds)</label>
            <input type="number" id="idle_timeout" value="{idle_timeout}" min="0" onchange="saveSetting('idle_timeout', this.value)">
            <div class="hint">Seconds before sleep mode (0 = disabled)</div>
        </div>

        <div class="form-group">
            <label>Rate Limit Attempts</label>
            <input type="number" id="rate_limit_attempts" value="{rate_limit_attempts}" min="1" onchange="saveSetting('rate_limit_attempts', this.value)">
            <div class="hint">Auth attempts before lockout</div>
        </div>

        <div class="form-group">
            <label>Rate Limit Window (seconds)</label>
            <input type="number" id="rate_limit_window" value="{rate_limit_window}" min="1" onchange="saveSetting('rate_limit_window', this.value)">
            <div class="hint">Time window for rate limiting</div>
        </div>
    </div>

    <div class="card">
        <h2 class="section-title">TLS/Encryption</h2>

        <div class="form-group toggle-switch">
            <input type="checkbox" id="tls_enabled" {tls_enabled_checked} onchange="saveSetting('tls_enabled', this.checked ? '1' : '0')">
            <label for="tls_enabled">TLS Enabled</label>
        </div>
        <div class="hint" style="margin-bottom: 20px;">Use wss:// instead of ws://</div>

        <div class="form-group toggle-switch">
            <input type="checkbox" id="mtls_enabled" {mtls_enabled_checked} onchange="saveSetting('mtls_enabled', this.checked ? '1' : '0')">
            <label for="mtls_enabled">mTLS (Client Certs)</label>
        </div>
        <div class="hint" style="margin-bottom: 20px;">Require client certificates for auth</div>

        <div class="form-group">
            <label>Token Rotation (days)</label>
            <input type="number" id="token_rotation_days" value="{token_rotation_days}" min="0" onchange="saveSetting('token_rotation_days', this.value)">
            <div class="hint">Days before auto-rotation (0 = disabled)</div>
        </div>

        <div class="form-group">
            <label>Token Grace Period (hours)</label>
            <input type="number" id="token_grace_hours" value="{token_grace_hours}" min="0" onchange="saveSetting('token_grace_hours', this.value)">
            <div class="hint">Hours old tokens remain valid after rotation</div>
        </div>
    </div>
</div>

<script>
const SESSION = '{session_token}';
function saveSetting(key, value) {{
    const status = document.getElementById('save-status');
    status.style.display = 'block';
    status.style.background = 'rgba(0, 212, 255, 0.2)';
    status.style.border = '1px solid var(--accent)';
    status.style.color = 'var(--accent)';
    status.textContent = 'Saving...';

    fetch('/admin/config/set?session=' + SESSION + '&key=' + encodeURIComponent(key) + '&value=' + encodeURIComponent(value))
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                status.style.background = 'rgba(0, 255, 136, 0.2)';
                status.style.border = '1px solid var(--success)';
                status.style.color = 'var(--success)';
                status.textContent = 'Saved!';
            }} else {{
                status.style.background = 'rgba(255, 68, 102, 0.2)';
                status.style.border = '1px solid var(--danger)';
                status.style.color = 'var(--danger)';
                status.textContent = 'Error: ' + (data.error || 'Unknown');
            }}
            setTimeout(() => status.style.display = 'none', 2000);
        }})
        .catch(err => {{
            status.style.background = 'rgba(255, 68, 102, 0.2)';
            status.style.border = '1px solid var(--danger)';
            status.style.color = 'var(--danger)';
            status.textContent = 'Error saving';
            setTimeout(() => status.style.display = 'none', 2000);
        }});
}}
</script>

<p class="refresh-note"><a href="/admin/logout" style="color: var(--accent);">Logout</a></p>
"""


def generate_web_pin() -> str:
    """Generate a 6-digit PIN for web admin login."""
    return ''.join(str(secrets.randbelow(10)) for _ in range(6))


class WebAdminHandler:
    """Handle HTTP requests for the web admin dashboard."""

    # Class-level PIN that persists across handler instances
    _web_pin: Optional[str] = None
    # Class-level authenticated sessions (must be class-level to persist across instances)
    _authenticated_sessions: set = set()
    _start_time: Optional[float] = None

    def __init__(self, config, server_instance=None):
        self.config = config
        self.server = server_instance

        # Set start time once on first handler creation
        if WebAdminHandler._start_time is None:
            WebAdminHandler._start_time = time.time()

        # Generate PIN once on first handler creation
        if WebAdminHandler._web_pin is None:
            WebAdminHandler._web_pin = generate_web_pin()

    @classmethod
    def get_web_pin(cls) -> str:
        """Get the current web PIN, generating one if needed."""
        if cls._web_pin is None:
            cls._web_pin = generate_web_pin()
            cls._save_pin_to_file(cls._web_pin)
        return cls._web_pin

    @classmethod
    def regenerate_pin(cls) -> str:
        """Regenerate the web PIN."""
        cls._web_pin = generate_web_pin()
        cls._save_pin_to_file(cls._web_pin)
        return cls._web_pin

    @classmethod
    def _save_pin_to_file(cls, pin: str):
        """Save the PIN to a file for daemon mode access."""
        from pathlib import Path
        try:
            pin_dir = Path.home() / '.darkcode'
            pin_dir.mkdir(parents=True, exist_ok=True)
            pin_file = pin_dir / 'web_pin'
            pin_file.write_text(pin)
            pin_file.chmod(0o600)  # Only owner can read
        except Exception:
            pass  # Non-critical

    @classmethod
    def load_pin_from_file(cls) -> Optional[str]:
        """Load the PIN from file (for CLI access to running daemon)."""
        from pathlib import Path
        try:
            pin_file = Path.home() / '.darkcode' / 'web_pin'
            if pin_file.exists():
                return pin_file.read_text().strip()
        except Exception:
            pass
        return None

    def _is_daemon_mode(self) -> bool:
        """Check if the server is running in daemon mode."""
        from pathlib import Path
        pid_file = self.config.config_dir / 'darkcode.pid'
        return pid_file.exists()

    def _generate_session_cookie(self) -> str:
        """Generate a random session cookie."""
        return secrets.token_urlsafe(32)

    def _is_authenticated(self, cookies: dict) -> bool:
        """Check if the request has a valid session cookie."""
        session_id = cookies.get('darkcode_admin_session')
        return session_id in WebAdminHandler._authenticated_sessions

    def _verify_pin(self, pin: str) -> bool:
        """Verify the provided PIN matches the web PIN."""
        if WebAdminHandler._web_pin is None:
            return False
        # Simple string comparison - strip whitespace from input
        return pin.strip() == WebAdminHandler._web_pin

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
            # Check for session token in query params (from login redirect)
            session_from_url = query_params.get('session', [None])[0]
            rotated = query_params.get('rotated', [None])[0]
            message = ''
            if rotated:
                message = '<div class="success">Token rotated successfully! Update your app with the new token.</div>'

            if session_from_url and session_from_url in WebAdminHandler._authenticated_sessions:
                return self._dashboard_page(session_token=session_from_url, message=message)

            # Check for session in cookie
            if self._is_authenticated(cookies):
                return self._dashboard_page(message=message)
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
                    WebAdminHandler._authenticated_sessions.add(session_cookie)
                    # Redirect with session token in URL
                    return (
                        302,
                        {
                            'Location': f'/admin?session={session_cookie}',
                            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'
                        },
                        b''
                    )
                else:
                    return self._login_page(error="Invalid PIN")
            else:
                return self._login_page()

        elif clean_path == '/admin/logout':
            session_id = cookies.get('darkcode_admin_session')
            if session_id:
                WebAdminHandler._authenticated_sessions.discard(session_id)
            return (
                302,
                {
                    'Location': '/admin',
                    'Set-Cookie': 'darkcode_admin_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'
                },
                b''
            )

        elif clean_path == '/admin/api/status':
            if not self._is_authenticated(cookies):
                return (401, {'Content-Type': 'application/json'}, b'{"error": "Unauthorized"}')
            return self._api_status()

        elif clean_path == '/admin/unbind':
            if not self._is_authenticated(cookies):
                return self._login_page()
            return self._unbind_device()

        elif clean_path == '/admin/config':
            # Redirect to main dashboard - all settings are now there
            session_from_url = query_params.get('session', [None])[0]
            if session_from_url:
                return (302, {'Location': f'/admin?session={session_from_url}'}, b'')
            return (302, {'Location': '/admin'}, b'')

        elif clean_path == '/admin/config/save':
            session_from_url = query_params.get('session', [None])[0]
            if not (session_from_url and session_from_url in WebAdminHandler._authenticated_sessions):
                if not self._is_authenticated(cookies):
                    return self._login_page()
                session_from_url = cookies.get('darkcode_admin_session')
            if method == 'POST' and body:
                return self._save_config(body, session_from_url)
            return self._config_page(session_token=session_from_url)

        elif clean_path == '/admin/config/rotate-token':
            session_from_url = query_params.get('session', [None])[0]
            if not (session_from_url and session_from_url in WebAdminHandler._authenticated_sessions):
                if not self._is_authenticated(cookies):
                    return self._login_page()
                session_from_url = cookies.get('darkcode_admin_session')
            return self._rotate_token(session_from_url)

        elif clean_path == '/admin/config/set':
            session_from_url = query_params.get('session', [None])[0]
            if not (session_from_url and session_from_url in WebAdminHandler._authenticated_sessions):
                if not self._is_authenticated(cookies):
                    return (401, {'Content-Type': 'application/json'}, b'{"success": false, "error": "Unauthorized"}')
            key = query_params.get('key', [None])[0]
            value = query_params.get('value', [''])[0]
            return self._set_config_value(key, value)

        elif clean_path == '/admin/logs':
            session_from_url = query_params.get('session', [None])[0]
            if not (session_from_url and session_from_url in WebAdminHandler._authenticated_sessions):
                if not self._is_authenticated(cookies):
                    return (401, {'Content-Type': 'text/plain'}, b'Unauthorized')
            logs = self._get_recent_logs()
            return (200, {'Content-Type': 'text/plain'}, logs.encode('utf-8'))

        elif clean_path == '/admin/logs/download':
            session_from_url = query_params.get('session', [None])[0]
            if not (session_from_url and session_from_url in WebAdminHandler._authenticated_sessions):
                if not self._is_authenticated(cookies):
                    return (401, {'Content-Type': 'text/plain'}, b'Unauthorized')
            logs = self._get_full_logs()
            return (200, {
                'Content-Type': 'text/plain',
                'Content-Disposition': 'attachment; filename="darkcode-server.log"'
            }, logs.encode('utf-8'))

        else:
            return (404, {'Content-Type': 'text/html'}, b'Not Found')

    def _serve_logo(self) -> tuple:
        """Serve the embedded DarkCode logo."""
        logo_data = base64.b64decode(LOGO_B64)
        return (200, {'Content-Type': 'image/png', 'Cache-Control': 'max-age=3600'}, logo_data)

    def _login_page(self, error: str = '') -> tuple:
        """Render the login page."""
        error_html = f'<div class="error">{html.escape(error)}</div>' if error else ''
        content = LOGIN_CONTENT.format(error=error_html, ascii_logo=html.escape(ASCII_LOGO))
        page = ADMIN_HTML.format(content=content)
        return (200, {
            'Content-Type': 'text/html',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache'
        }, page.encode('utf-8'))

    def _dashboard_page(self, session_token: str = None, message: str = '') -> tuple:
        """Render the main dashboard."""
        # Calculate uptime
        uptime_secs = int(time.time() - (WebAdminHandler._start_time or time.time()))
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

        # Bound device info
        bound_device = 'None'
        unbind_button = ''
        if self.config.bound_device_id:
            bound_device = self.config.bound_device_id[:12] + '...'
            unbind_button = '''
            <div class="actions" style="margin-top: 15px;">
                <button class="btn btn-danger" onclick="if(confirm('Unbind device? This will allow a new device to connect.')) location.href='/admin/unbind'">Unbind Device</button>
            </div>
            '''

        # Generate QR code for quick connect
        try:
            qr_code_base64 = generate_qr_png_base64(self.config, "direct")
        except Exception:
            qr_code_base64 = ""

        # Get log content
        log_content = self._get_recent_logs()

        # Permission mode selected states
        perm_mode = getattr(self.config, 'permission_mode', 'default')
        perm_default = 'selected' if perm_mode == 'default' else ''
        perm_accept = 'selected' if perm_mode == 'acceptEdits' else ''
        perm_bypass = 'selected' if perm_mode == 'bypassPermissions' else ''

        # Detect daemon mode by checking for PID file
        is_daemon = self._is_daemon_mode()
        daemon_mode = 'Daemon' if is_daemon else 'Foreground'
        daemon_mode_color = 'var(--success)' if is_daemon else 'var(--warning)'

        content = DASHBOARD_CONTENT.format(
            ascii_logo=html.escape(ASCII_LOGO),
            message=message,
            daemon_mode=daemon_mode,
            daemon_mode_color=daemon_mode_color,
            uptime=uptime,
            port=self.config.port,
            working_dir=str(self.config.working_dir),
            server_name=getattr(self.config, 'server_name', 'DarkCode Server'),
            perm_default=perm_default,
            perm_accept=perm_accept,
            perm_bypass=perm_bypass,
            state=state,
            device_lock_checked='checked' if self.config.device_lock else '',
            tls_enabled_checked='checked' if self.config.tls_enabled else '',
            max_sessions_per_ip=getattr(self.config, 'max_sessions_per_ip', 5),
            idle_timeout=getattr(self.config, 'idle_timeout', 0),
            unbind_button=unbind_button,
            session_count=session_count,
            sessions_html=sessions_html,
            token_masked=self.config.token[:4] + '*' * 20 + self.config.token[-4:],
            token_full=self.config.token,
            local_ip=local_ip,
            tailscale_row=tailscale_row,
            ws_url=ws_url,
            session_token=session_token or '',
            qr_code_base64=qr_code_base64,
            log_content=log_content,
        )

        page = ADMIN_HTML.format(content=content)
        return (200, {'Content-Type': 'text/html'}, page.encode('utf-8'))

    def _unbind_device(self) -> tuple:
        """Unbind the current device and redirect back to dashboard."""
        if self.server and hasattr(self.server, 'unbind_device'):
            self.server.unbind_device()
        elif self.config.bound_device_id:
            # Fallback: directly modify config
            self.config.bound_device_id = None
            self.config.save()

        return (
            302,
            {'Location': '/admin'},
            b''
        )

    def _api_status(self) -> tuple:
        """Return status as JSON for API consumers."""
        uptime_secs = int(time.time() - (WebAdminHandler._start_time or time.time()))
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

    def _get_log_path(self) -> str:
        """Get the path to the log file."""
        from pathlib import Path
        log_dir = self.config.working_dir / '.darkcode'
        log_file = log_dir / 'server.log'
        if log_file.exists():
            return str(log_file)
        # Try common log locations
        for path in [
            Path.home() / '.darkcode' / 'server.log',
            Path('/tmp') / 'darkcode-server.log',
        ]:
            if path.exists():
                return str(path)
        return ''

    def _get_recent_logs(self, lines: int = 50) -> str:
        """Get the last N lines of the log file."""
        log_path = self._get_log_path()
        if not log_path:
            return 'No log file found. Logs will appear here when available.'
        try:
            with open(log_path, 'r') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception as e:
            return f'Error reading logs: {e}'

    def _get_full_logs(self) -> str:
        """Get the full log file content."""
        log_path = self._get_log_path()
        if not log_path:
            return 'No log file found.'
        try:
            with open(log_path, 'r') as f:
                return f.read()
        except Exception as e:
            return f'Error reading logs: {e}'

    def _config_page(self, session_token: str = None, message: str = '') -> tuple:
        """Render the configuration page."""
        from pathlib import Path

        # Permission mode selected states
        perm_default = 'selected' if self.config.permission_mode == 'default' else ''
        perm_accept = 'selected' if self.config.permission_mode == 'acceptEdits' else ''
        perm_bypass = 'selected' if self.config.permission_mode == 'bypassPermissions' else ''

        # Unbind button (only show if device is bound)
        unbind_button = ''
        if self.config.bound_device_id:
            unbind_button = f'''
            <button type="button" class="btn btn-danger" onclick="if(confirm('Unbind device? A new device will be able to connect.')) location.href='/admin/unbind?session={session_token}'">
                Unbind Device
            </button>
            '''

        content = CONFIG_CONTENT.format(
            session_token=session_token or '',
            message=message,
            port=self.config.port,
            working_dir=html.escape(str(self.config.working_dir)),
            browse_dir=html.escape(str(self.config.browse_dir)) if self.config.browse_dir else '',
            server_name=html.escape(self.config.server_name),
            permission_mode=self.config.permission_mode,
            perm_default=perm_default,
            perm_accept=perm_accept,
            perm_bypass=perm_bypass,
            device_lock_checked='checked' if self.config.device_lock else '',
            local_only_checked='checked' if self.config.local_only else '',
            max_sessions_per_ip=self.config.max_sessions_per_ip,
            idle_timeout=self.config.idle_timeout,
            rate_limit_attempts=self.config.rate_limit_attempts,
            rate_limit_window=self.config.rate_limit_window,
            tls_enabled_checked='checked' if self.config.tls_enabled else '',
            mtls_enabled_checked='checked' if self.config.mtls_enabled else '',
            token_rotation_days=self.config.token_rotation_days,
            token_grace_hours=self.config.token_grace_hours,
            token_masked=self.config.token[:4] + '*' * 20 + self.config.token[-4:],
            unbind_button=unbind_button,
        )

        page = ADMIN_HTML.format(content=content)
        return (200, {'Content-Type': 'text/html'}, page.encode('utf-8'))

    def _save_config(self, body: bytes, session_token: str) -> tuple:
        """Save configuration from form data."""
        from pathlib import Path
        from urllib.parse import unquote_plus

        form_data = self._parse_form_data(body)

        try:
            # Update server settings
            if 'port' in form_data:
                port = int(form_data['port'])
                if 1 <= port <= 65535:
                    self.config.port = port

            if 'working_dir' in form_data:
                working_dir = unquote_plus(form_data['working_dir'])
                if working_dir:
                    path = Path(working_dir)
                    if path.exists() and path.is_dir():
                        self.config.working_dir = path

            if 'browse_dir' in form_data:
                browse_dir = unquote_plus(form_data['browse_dir'])
                if browse_dir:
                    path = Path(browse_dir)
                    if path.exists() and path.is_dir():
                        self.config.browse_dir = path
                else:
                    self.config.browse_dir = None

            if 'server_name' in form_data:
                name = unquote_plus(form_data['server_name'])
                if name:
                    self.config.server_name = name

            if 'permission_mode' in form_data:
                mode = form_data['permission_mode']
                if mode in ('default', 'acceptEdits', 'bypassPermissions'):
                    self.config.permission_mode = mode

            # Update security settings (checkboxes - present = true, absent = false)
            self.config.device_lock = 'device_lock' in form_data
            self.config.local_only = 'local_only' in form_data

            if 'max_sessions_per_ip' in form_data:
                val = int(form_data['max_sessions_per_ip'])
                if 1 <= val <= 100:
                    self.config.max_sessions_per_ip = val

            if 'idle_timeout' in form_data:
                val = int(form_data['idle_timeout'])
                if val >= 0:
                    self.config.idle_timeout = val

            if 'rate_limit_attempts' in form_data:
                val = int(form_data['rate_limit_attempts'])
                if val >= 1:
                    self.config.rate_limit_attempts = val

            if 'rate_limit_window' in form_data:
                val = int(form_data['rate_limit_window'])
                if val >= 1:
                    self.config.rate_limit_window = val

            # Update TLS settings
            self.config.tls_enabled = 'tls_enabled' in form_data
            self.config.mtls_enabled = 'mtls_enabled' in form_data

            if 'token_rotation_days' in form_data:
                val = int(form_data['token_rotation_days'])
                if val >= 0:
                    self.config.token_rotation_days = val

            if 'token_grace_hours' in form_data:
                val = int(form_data['token_grace_hours'])
                if val >= 0:
                    self.config.token_grace_hours = val

            # Save to disk
            self.config.save()

            message = '<div class="success">Configuration saved successfully! Restart server for some changes to take effect.</div>'
            return self._config_page(session_token=session_token, message=message)

        except Exception as e:
            message = f'<div class="error">Error saving configuration: {html.escape(str(e))}</div>'
            return self._config_page(session_token=session_token, message=message)

    def _set_config_value(self, key: str, value: str) -> tuple:
        """Set a single config value via AJAX."""
        from pathlib import Path
        from urllib.parse import unquote_plus
        import json

        try:
            value = unquote_plus(value)

            if key == 'port':
                port = int(value)
                if 1 <= port <= 65535:
                    self.config.port = port
            elif key == 'working_dir':
                if value:
                    path = Path(value)
                    if path.exists() and path.is_dir():
                        self.config.working_dir = path
            elif key == 'browse_dir':
                if value:
                    path = Path(value)
                    if path.exists() and path.is_dir():
                        self.config.browse_dir = path
                else:
                    self.config.browse_dir = None
            elif key == 'server_name':
                if value:
                    self.config.server_name = value
            elif key == 'permission_mode':
                if value in ('default', 'acceptEdits', 'bypassPermissions'):
                    self.config.permission_mode = value
            elif key == 'device_lock':
                self.config.device_lock = value == '1'
            elif key == 'local_only':
                self.config.local_only = value == '1'
            elif key == 'max_sessions_per_ip':
                val = int(value)
                if 1 <= val <= 100:
                    self.config.max_sessions_per_ip = val
            elif key == 'idle_timeout':
                val = int(value)
                if val >= 0:
                    self.config.idle_timeout = val
            elif key == 'rate_limit_attempts':
                val = int(value)
                if val >= 1:
                    self.config.rate_limit_attempts = val
            elif key == 'rate_limit_window':
                val = int(value)
                if val >= 1:
                    self.config.rate_limit_window = val
            elif key == 'tls_enabled':
                self.config.tls_enabled = value == '1'
            elif key == 'mtls_enabled':
                self.config.mtls_enabled = value == '1'
            elif key == 'token_rotation_days':
                val = int(value)
                if val >= 0:
                    self.config.token_rotation_days = val
            elif key == 'token_grace_hours':
                val = int(value)
                if val >= 0:
                    self.config.token_grace_hours = val
            else:
                return (400, {'Content-Type': 'application/json'}, json.dumps({'success': False, 'error': 'Unknown key'}).encode())

            self.config.save()
            return (200, {'Content-Type': 'application/json'}, json.dumps({'success': True}).encode())

        except Exception as e:
            return (500, {'Content-Type': 'application/json'}, json.dumps({'success': False, 'error': str(e)}).encode())

    def _rotate_token(self, session_token: str) -> tuple:
        """Generate a new auth token."""
        import secrets as sec
        self.config.token = sec.token_urlsafe(24)
        self.config.save()

        # Redirect back to dashboard with success message
        return (
            302,
            {'Location': f'/admin?session={session_token}&rotated=1'},
            b''
        )


def serve_favicon() -> tuple:
    """Serve the embedded favicon."""
    favicon_data = base64.b64decode(FAVICON_B64)
    return (200, {'Content-Type': 'image/png', 'Cache-Control': 'max-age=86400'}, favicon_data)
