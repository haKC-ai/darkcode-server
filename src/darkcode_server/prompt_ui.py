"""Interactive prompt UI using prompt_toolkit with dropdowns and multi-select."""

import os
import platform
from pathlib import Path
from typing import Optional, Tuple, List

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, FormattedTextControl
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.widgets import Label, Button, RadioList, CheckboxList, Frame, TextArea
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.shortcuts import radiolist_dialog, checkboxlist_dialog, button_dialog, input_dialog, yes_no_dialog, message_dialog
from rich.console import Console

console = Console()

# Style for the prompts
STYLE = Style.from_dict({
    'dialog': 'bg:#1e1e2e',
    'dialog.body': 'bg:#1e1e2e #cdd6f4',
    'dialog.body text-area': 'bg:#313244 #cdd6f4',
    'dialog shadow': 'bg:#11111b',
    'button': 'bg:#89b4fa #1e1e2e',
    'button.focused': 'bg:#f5c2e7 #1e1e2e bold',
    'radiolist': 'bg:#1e1e2e #cdd6f4',
    'checkbox': 'bg:#1e1e2e #cdd6f4',
    'frame.label': '#f5c2e7 bold',
})


def show_main_menu() -> Optional[str]:
    """Show the main menu with action selection."""
    result = radiolist_dialog(
        title=HTML('<style fg="#f5c2e7" bold="true">DarkCode Server</style>'),
        text="Select an action:",
        values=[
            ("start", "Start Server"),
            ("status", "Server Status"),
            ("qr", "Show QR Code"),
            ("guest", "Guest Codes"),
            ("config", "Configuration"),
            ("security", "Security Settings"),
            ("setup", "Setup Wizard"),
            ("exit", "Exit"),
        ],
        style=STYLE,
    ).run()

    return result


def show_connection_mode_menu(tailscale_ip: Optional[str] = None) -> Optional[str]:
    """Show connection mode selection dialog."""
    values = [
        ("direct", "Direct LAN - Connect over local network"),
    ]

    if tailscale_ip:
        values.append(("tailscale", f"Tailscale ({tailscale_ip}) - Secure mesh VPN"))
    else:
        values.append(("tailscale", "Tailscale - Not detected (install first)"))

    values.append(("ssh", "SSH Tunnel - Localhost only, most secure"))

    result = radiolist_dialog(
        title=HTML('<style fg="#89b4fa" bold="true">Connection Mode</style>'),
        text="How will you connect to the server?",
        values=values,
        style=STYLE,
    ).run()

    return result


def show_security_options() -> Optional[List[str]]:
    """Show security options as multi-select checkboxes."""
    result = checkboxlist_dialog(
        title=HTML('<style fg="#f38ba8" bold="true">Security Options</style>'),
        text="Select security features to enable:",
        values=[
            ("device_lock", "Device Lock - Only allow first connected device"),
            ("tls", "TLS Encryption - Use wss:// instead of ws://"),
            ("mtls", "mTLS - Require client certificates"),
            ("token_rotation", "Token Rotation - Auto-rotate auth tokens"),
        ],
        style=STYLE,
    ).run()

    return result


def show_guest_menu() -> Optional[str]:
    """Show guest code management menu."""
    result = radiolist_dialog(
        title=HTML('<style fg="#a6e3a1" bold="true">Guest Access Codes</style>'),
        text="Manage guest access:",
        values=[
            ("create", "Create New Code"),
            ("list", "List All Codes"),
            ("revoke", "Revoke a Code"),
            ("qr", "Show QR for Code"),
            ("back", "Back to Main Menu"),
        ],
        style=STYLE,
    ).run()

    return result


def show_guest_create_dialog() -> Optional[dict]:
    """Show dialog to create a new guest code."""
    # Get guest name
    name = input_dialog(
        title="Create Guest Code",
        text="Enter friend's name:",
        style=STYLE,
    ).run()

    if not name:
        return None

    # Get expiration
    expires = radiolist_dialog(
        title="Expiration",
        text="When should the code expire?",
        values=[
            ("1", "1 hour"),
            ("24", "24 hours"),
            ("168", "1 week"),
            ("0", "Never"),
        ],
        style=STYLE,
    ).run()

    if expires is None:
        return None

    # Get permissions
    permissions = radiolist_dialog(
        title="Permissions",
        text="What can the guest do?",
        values=[
            ("full", "Full Access - Read and execute commands"),
            ("read_only", "Read Only - View files and output only"),
        ],
        style=STYLE,
    ).run()

    if permissions is None:
        return None

    return {
        "name": name,
        "expires_hours": int(expires) if expires != "0" else None,
        "permission_level": permissions,
    }


def show_config_editor(config: dict) -> Optional[dict]:
    """Show configuration editor dialog."""
    # Port
    port = input_dialog(
        title="Server Port",
        text="Enter server port:",
        default=str(config.get("port", 3100)),
        style=STYLE,
    ).run()

    if port is None:
        return None

    # Working directory
    working_dir = input_dialog(
        title="Working Directory",
        text="Enter working directory:",
        default=str(config.get("working_dir", Path.cwd())),
        style=STYLE,
    ).run()

    if working_dir is None:
        return None

    # Server name
    name = input_dialog(
        title="Server Name",
        text="Enter server display name:",
        default=config.get("server_name", platform.node()),
        style=STYLE,
    ).run()

    if name is None:
        return None

    return {
        "port": int(port),
        "working_dir": working_dir,
        "server_name": name,
    }


def confirm_action(title: str, message: str) -> bool:
    """Show a yes/no confirmation dialog."""
    return yes_no_dialog(
        title=title,
        text=message,
        style=STYLE,
    ).run()


def show_message(title: str, message: str):
    """Show an info message dialog."""
    message_dialog(
        title=title,
        text=message,
        style=STYLE,
    ).run()


def run_interactive_menu() -> Optional[Tuple[str, Optional[str]]]:
    """Run the full interactive menu flow.

    Returns:
        Tuple of (action, mode) where action is what to do and mode is connection mode.
        Returns None if user exits.
    """
    from darkcode_server.config import ServerConfig

    while True:
        action = show_main_menu()

        if action is None or action == "exit":
            return None

        if action == "start":
            # Get connection mode
            config = ServerConfig.load()
            tailscale_ip = config.get_tailscale_ip()
            mode = show_connection_mode_menu(tailscale_ip)

            if mode is None:
                continue

            if mode == "tailscale" and not tailscale_ip:
                if confirm_action("Install Tailscale?",
                    "Tailscale is not installed. Would you like to install it now?"):
                    return ("install_tailscale", None)
                continue

            return ("start", mode)

        elif action == "guest":
            guest_action = show_guest_menu()
            if guest_action and guest_action != "back":
                return (f"guest_{guest_action}", None)

        else:
            return (action, None)
