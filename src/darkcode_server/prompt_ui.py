"""Interactive split-pane TUI using prompt_toolkit."""

import asyncio
import io
import platform
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Optional, Callable

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import Frame, TextArea, Box
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, FormattedText, ANSI


# Catppuccin-inspired theme
STYLE = Style.from_dict({
    # Base
    'frame': 'bg:#1e1e2e #cdd6f4',
    'frame.border': '#89b4fa',
    'frame.label': '#f5c2e7 bold',

    # Menu
    'menu': 'bg:#1e1e2e #cdd6f4',
    'menu.selected': 'bg:#313244 #f5c2e7 bold',
    'menu.item': '#cdd6f4',
    'menu.key': '#89b4fa bold',

    # Output
    'output': 'bg:#11111b #cdd6f4',
    'output.title': '#a6e3a1 bold',
    'output.info': '#89b4fa',
    'output.success': '#a6e3a1',
    'output.warning': '#f9e2af',
    'output.error': '#f38ba8',

    # Status bar
    'status': 'bg:#313244 #cdd6f4',
    'status.key': '#f5c2e7 bold',
})


class SplitPaneTUI:
    """Split-pane terminal UI with menu on left and output on right."""

    def __init__(self):
        self.selected_index = 0
        self.output_lines = []
        self.running = True
        self.current_submenu = None  # None = main menu, or submenu name

        # Menu items: (key, label, action_name)
        self.main_menu = [
            ('1', 'Start Server', 'start'),
            ('2', 'Server Status', 'status'),
            ('3', 'Show QR Code', 'qr'),
            ('4', 'Guest Codes', 'guest'),
            ('5', 'Configuration', 'config'),
            ('6', 'Security', 'security'),
            ('7', 'Setup Wizard', 'setup'),
            ('q', 'Quit', 'quit'),
        ]

        self.guest_menu = [
            ('1', 'Create New Code', 'guest_create'),
            ('2', 'List All Codes', 'guest_list'),
            ('3', 'Revoke a Code', 'guest_revoke'),
            ('4', 'Show QR for Code', 'guest_qr'),
            ('b', 'Back', 'back'),
        ]

        self.connection_menu = [
            ('1', 'Direct LAN', 'direct'),
            ('2', 'Tailscale', 'tailscale'),
            ('3', 'SSH Tunnel', 'ssh'),
            ('b', 'Back', 'back'),
        ]

        self.security_menu = [
            ('1', 'Security Status', 'security_status'),
            ('2', 'Toggle TLS', 'security_tls'),
            ('3', 'Toggle mTLS', 'security_mtls'),
            ('4', 'Toggle Device Lock', 'security_device_lock'),
            ('5', 'Reset Auth Token', 'security_reset_token'),
            ('6', 'View Blocked IPs', 'security_blocked'),
            ('7', 'Unbind Device', 'security_unbind'),
            ('b', 'Back', 'back'),
        ]

        self._build_app()

    @property
    def current_menu(self):
        """Get the current menu items."""
        if self.current_submenu == 'guest':
            return self.guest_menu
        elif self.current_submenu == 'connection':
            return self.connection_menu
        elif self.current_submenu == 'security':
            return self.security_menu
        return self.main_menu

    @property
    def menu_title(self):
        """Get the current menu title."""
        if self.current_submenu == 'guest':
            return 'Guest Codes'
        elif self.current_submenu == 'connection':
            return 'Connection Mode'
        elif self.current_submenu == 'security':
            return 'Security'
        return 'DarkCode Server'

    def _get_menu_text(self):
        """Generate the menu text."""
        lines = []
        menu = self.current_menu

        for i, (key, label, _) in enumerate(menu):
            if i == self.selected_index:
                lines.append(('class:menu.selected', f' [{key}] {label} \n'))
            else:
                lines.append(('class:menu.item', f' '))
                lines.append(('class:menu.key', f'[{key}]'))
                lines.append(('class:menu.item', f' {label}\n'))

        return lines

    def _get_output_text(self):
        """Generate the output panel text."""
        if not self.output_lines:
            return [('class:output.info', '\n  Select an option from the menu\n  to see output here.\n\n'),
                    ('class:output', '  Use ↑↓ or number keys to navigate\n'),
                    ('class:output', '  Press Enter to select\n'),
                    ('class:output', '  Press q to quit\n')]

        result = []
        for line in self.output_lines[-50:]:  # Keep last 50 lines
            if line.startswith('[OK]') or line.startswith('[SUCCESS]') or line.startswith('✓'):
                result.append(('class:output.success', line + '\n'))
            elif line.startswith('[ERROR]') or line.startswith('[FAIL]') or line.startswith('✗'):
                result.append(('class:output.error', line + '\n'))
            elif line.startswith('[WARN]') or line.startswith('⚠'):
                result.append(('class:output.warning', line + '\n'))
            elif line.startswith('###') or line.startswith('==='):
                result.append(('class:output.title', line + '\n'))
            else:
                result.append(('class:output', line + '\n'))
        return result

    def _get_status_text(self):
        """Generate status bar text."""
        return [
            ('class:status', ' '),
            ('class:status.key', '↑↓'),
            ('class:status', ' Navigate  '),
            ('class:status.key', 'Enter'),
            ('class:status', ' Select  '),
            ('class:status.key', 'q'),
            ('class:status', ' Quit '),
        ]

    def add_output(self, text: str):
        """Add text to the output panel."""
        for line in text.split('\n'):
            if line.strip():
                self.output_lines.append(line)
        self.app.invalidate()

    def clear_output(self):
        """Clear the output panel."""
        self.output_lines = []
        self.app.invalidate()

    def _build_app(self):
        """Build the prompt_toolkit application."""
        kb = KeyBindings()

        @kb.add('up')
        def _(event):
            self.selected_index = (self.selected_index - 1) % len(self.current_menu)

        @kb.add('down')
        def _(event):
            self.selected_index = (self.selected_index + 1) % len(self.current_menu)

        @kb.add('enter')
        def _(event):
            self._execute_selection()

        @kb.add('q')
        def _(event):
            if self.current_submenu:
                self.current_submenu = None
                self.selected_index = 0
            else:
                self.running = False
                event.app.exit()

        @kb.add('escape')
        def _(event):
            if self.current_submenu:
                self.current_submenu = None
                self.selected_index = 0
            else:
                self.running = False
                event.app.exit()

        # Number key shortcuts
        for i in range(1, 10):
            @kb.add(str(i))
            def _(event, idx=i):
                menu = self.current_menu
                if idx <= len(menu):
                    self.selected_index = idx - 1
                    self._execute_selection()

        @kb.add('b')
        def _(event):
            if self.current_submenu:
                self.current_submenu = None
                self.selected_index = 0

        # Layout
        menu_window = Frame(
            Window(
                FormattedTextControl(self._get_menu_text),
                width=Dimension(min=30, preferred=35),
            ),
            title=lambda: self.menu_title,
            style='class:frame',
        )

        output_window = Frame(
            Window(
                FormattedTextControl(self._get_output_text),
                wrap_lines=True,
            ),
            title='Output',
            style='class:frame',
        )

        status_bar = Window(
            FormattedTextControl(self._get_status_text),
            height=1,
            style='class:status',
        )

        root = HSplit([
            VSplit([
                menu_window,
                output_window,
            ]),
            status_bar,
        ])

        self.app = Application(
            layout=Layout(root),
            key_bindings=kb,
            style=STYLE,
            full_screen=True,
            mouse_support=True,
        )

    def _execute_selection(self):
        """Execute the currently selected menu item."""
        menu = self.current_menu
        if self.selected_index >= len(menu):
            return

        _, _, action = menu[self.selected_index]

        # Handle navigation
        if action == 'quit':
            self.running = False
            self.app.exit()
            return
        elif action == 'back':
            self.current_submenu = None
            self.selected_index = 0
            return
        elif action == 'guest':
            self.current_submenu = 'guest'
            self.selected_index = 0
            return
        elif action == 'start':
            self.current_submenu = 'connection'
            self.selected_index = 0
            self.add_output('=== Select Connection Mode ===')
            return
        elif action == 'security':
            self.current_submenu = 'security'
            self.selected_index = 0
            return

        # Execute action
        self._run_action(action)

    def _run_action(self, action: str):
        """Run an action and display output."""
        self.clear_output()
        self.add_output(f'=== {action.replace("_", " ").title()} ===')

        try:
            if action == 'status':
                self._show_status()
            elif action == 'qr':
                self._show_qr()
            elif action == 'config':
                self._show_config()
            elif action == 'setup':
                self.add_output('Run: darkcode setup')
                self.add_output('(Exiting to run setup wizard...)')
                self.running = False
                self.app.exit(result=('setup', None))
            elif action in ('direct', 'tailscale', 'ssh'):
                self._start_server(action)
            elif action == 'guest_create':
                self._guest_create()
            elif action == 'guest_list':
                self._guest_list()
            elif action == 'guest_revoke':
                self.add_output('Run: darkcode guest revoke <CODE>')
            elif action == 'guest_qr':
                self.add_output('Run: darkcode guest qr <CODE>')
            elif action == 'security_status':
                self._security_status()
            elif action == 'security_tls':
                self._toggle_tls()
            elif action == 'security_mtls':
                self._toggle_mtls()
            elif action == 'security_device_lock':
                self._toggle_device_lock()
            elif action == 'security_reset_token':
                self._reset_token()
            elif action == 'security_blocked':
                self._show_blocked()
            elif action == 'security_unbind':
                self._unbind_device()
            else:
                self.add_output(f'Action not implemented: {action}')
        except Exception as e:
            self.add_output(f'[ERROR] {e}')

    def _show_status(self):
        """Show server status."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()

        self.add_output(f'Port: {config.port}')
        self.add_output(f'Working Dir: {config.working_dir}')
        self.add_output(f'Server Name: {config.server_name}')
        self.add_output(f'TLS: {"enabled" if config.tls_enabled else "disabled"}')
        self.add_output(f'Device Lock: {"enabled" if config.device_lock else "disabled"}')

        # Check Tailscale
        tailscale_ip = config.get_tailscale_ip()
        if tailscale_ip:
            self.add_output(f'Tailscale: {tailscale_ip}')
        else:
            self.add_output('Tailscale: not detected')

        # Check for running daemon
        try:
            from darkcode_server.daemon import DarkCodeDaemon
            pid = DarkCodeDaemon.get_running_pid(config)
            if pid:
                self.add_output(f'[OK] Daemon running (PID {pid})')
            else:
                self.add_output('Daemon: not running')
        except:
            pass

    def _show_qr(self):
        """Show QR code info."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()

        self.add_output(f'Server: {config.server_name}')
        self.add_output(f'Port: {config.port}')
        self.add_output(f'Token: {config.token[:8]}...')

        local_ips = config.get_local_ips()
        for ip_info in local_ips:
            self.add_output(f'  {ip_info["interface"]}: {ip_info["address"]}')

        tailscale_ip = config.get_tailscale_ip()
        if tailscale_ip:
            self.add_output(f'  Tailscale: {tailscale_ip}')

        self.add_output('')
        self.add_output('Run: darkcode qr')
        self.add_output('to see scannable QR code')

    def _show_config(self):
        """Show configuration."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()

        self.add_output(f'Port: {config.port}')
        self.add_output(f'Working Dir: {config.working_dir}')
        self.add_output(f'Server Name: {config.server_name}')
        self.add_output(f'Config Dir: {config.config_dir}')
        self.add_output(f'Token: {config.token[:4]}{"*" * 16}')
        self.add_output(f'Max Sessions/IP: {config.max_sessions_per_ip}')
        self.add_output('')
        self.add_output('Run: darkcode config')
        self.add_output('to edit configuration')

    def _start_server(self, mode: str):
        """Start the server with selected mode."""
        self.add_output(f'Starting server in {mode} mode...')
        self.add_output('')
        self.running = False
        self.app.exit(result=('start', mode))

    def _guest_create(self):
        """Show guest create info."""
        self.add_output('Run: darkcode guest create "Name"')
        self.add_output('')
        self.add_output('Options:')
        self.add_output('  --expires 24     Hours until expiration')
        self.add_output('  --max-uses 5     Maximum uses')
        self.add_output('  --read-only      Read-only access')

    def _guest_list(self):
        """List guest codes."""
        try:
            from darkcode_server.config import ServerConfig
            from darkcode_server.security import GuestAccessManager

            config = ServerConfig.load()
            guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
            codes = guest_mgr.list_codes()

            if not codes:
                self.add_output('No guest codes found.')
                self.add_output('')
                self.add_output('Create one with:')
                self.add_output('  darkcode guest create "Name"')
            else:
                for code in codes:
                    status = 'active'
                    if not code.get('is_active'):
                        status = 'revoked'
                    elif code.get('expired'):
                        status = 'expired'

                    self.add_output(f'{code["code"]} - {code["name"]} [{status}]')
        except Exception as e:
            self.add_output(f'[ERROR] {e}')

    def _security_status(self):
        """Show security status."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()

        self.add_output(f'Device Lock: {"[OK] enabled" if config.device_lock else "disabled"}')
        self.add_output(f'Bound Device: {config.bound_device_id[:12] + "..." if config.bound_device_id else "none"}')
        self.add_output(f'TLS: {"[OK] enabled (wss://)" if config.tls_enabled else "disabled (ws://)"}')
        self.add_output(f'mTLS: {"[OK] enabled" if config.mtls_enabled else "disabled"}')
        self.add_output(f'Local Only: {"yes" if config.local_only else "no"}')
        self.add_output(f'Rate Limit: {config.rate_limit_attempts} attempts / {config.rate_limit_window}s')

    def _toggle_tls(self):
        """Toggle TLS setting."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()
        config.tls_enabled = not config.tls_enabled
        config.save()

        if config.tls_enabled:
            self.add_output('[OK] TLS enabled - Server will use wss://')
        else:
            self.add_output('[WARN] TLS disabled - Server will use ws://')

    def _toggle_mtls(self):
        """Toggle mTLS setting."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()
        config.mtls_enabled = not config.mtls_enabled
        if config.mtls_enabled:
            config.tls_enabled = True
        config.save()

        if config.mtls_enabled:
            self.add_output('[OK] mTLS enabled - Clients must present certificates')
        else:
            self.add_output('mTLS disabled')

    def _toggle_device_lock(self):
        """Toggle device lock setting."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()
        config.device_lock = not config.device_lock
        config.save()

        if config.device_lock:
            self.add_output('[OK] Device lock enabled')
            self.add_output('Server will lock to first connected device')
        else:
            self.add_output('Device lock disabled')

    def _reset_token(self):
        """Reset auth token."""
        import secrets
        from darkcode_server.config import ServerConfig

        config = ServerConfig.load()
        config.token = secrets.token_urlsafe(24)
        config.save()

        self.add_output('[OK] New token generated:')
        self.add_output(f'  {config.token}')
        self.add_output('')
        self.add_output('[WARN] Current connections will be invalidated')

    def _show_blocked(self):
        """Show blocked IPs/devices."""
        try:
            from darkcode_server.config import ServerConfig
            from darkcode_server.security import PersistentRateLimiter

            config = ServerConfig.load()
            db_path = config.config_dir / "security.db"

            if not db_path.exists():
                self.add_output('No security database yet.')
                return

            rate_limiter = PersistentRateLimiter(db_path)
            blocked = rate_limiter.get_blocked()

            if not blocked:
                self.add_output('[OK] No blocked IPs or devices')
            else:
                for b in blocked:
                    self.add_output(f'{b["identifier"][:20]} ({b["identifier_type"]})')
        except Exception as e:
            self.add_output(f'[ERROR] {e}')

    def _unbind_device(self):
        """Unbind current device."""
        from darkcode_server.config import ServerConfig
        config = ServerConfig.load()

        if not config.bound_device_id:
            self.add_output('No device is currently bound.')
            return

        config.bound_device_id = None
        config.save()

        self.add_output('[OK] Device unbound')
        self.add_output('Next device to authenticate will become bound device')

    def run(self):
        """Run the TUI application."""
        return self.app.run()


def run_interactive_menu():
    """Run the split-pane interactive menu.

    Returns:
        Tuple of (action, mode) or None if user quits.
    """
    tui = SplitPaneTUI()
    result = tui.run()
    return result
