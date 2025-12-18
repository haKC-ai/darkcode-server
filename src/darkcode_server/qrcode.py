"""QR code generation for easy mobile connection."""

import base64
import json
from typing import Optional

import qrcode
from rich.console import Console

from darkcode_server.config import ServerConfig


def generate_deep_link(config: ServerConfig, mode: str = "direct") -> str:
    """Generate a deep link URL for the mobile app."""
    ips = config.get_local_ips()
    tailscale_ip = config.get_tailscale_ip()

    if mode == "tailscale" and tailscale_ip:
        host = tailscale_ip
    elif ips:
        # Prefer non-docker interfaces
        preferred = next(
            (ip for ip in ips if "docker" not in ip.get("name", "").lower()),
            ips[0]
        )
        host = preferred["address"]
    else:
        host = "localhost"

    payload = {
        "name": config.server_name,
        "host": host,
        "port": config.port,
        "token": config.token,
        "mode": mode,
        "ts": int(__import__("time").time() * 1000),
    }

    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"darkcode://server/add?config={b64}"


def print_qr_code(config: ServerConfig, console: Console, mode: str = "direct"):
    """Print a QR code to the terminal."""
    deep_link = generate_deep_link(config, mode)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)

    # Convert to string
    lines = []
    for row in qr.get_matrix():
        line = ""
        for cell in row:
            line += "  " if cell else "\u2588\u2588"
        lines.append(line)

    # Print with rich
    for line in lines:
        console.print(line, style="white on white" if line.startswith("  ") else "black on white")

    return deep_link


def print_server_info(config: ServerConfig, console: Console):
    """Print server information with QR codes."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    # Server info table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    # Show bind address
    table.add_row("bind", f"{config.bind_host}:{config.port}")

    if config.local_only:
        # Local-only mode - only localhost
        table.add_row("mode", "[cyan]SSH Tunnel (localhost only)[/]")
    else:
        # Show all available IPs
        ips = config.get_local_ips()
        for ip_info in ips:
            table.add_row(ip_info["name"], f"ws://{ip_info['address']}:{config.port}")

        tailscale_ip = config.get_tailscale_ip()
        tailscale_hostname = config.get_tailscale_hostname()
        if tailscale_ip:
            table.add_row("tailscale", f"ws://{tailscale_ip}:{config.port}")
        if tailscale_hostname:
            table.add_row("hostname", tailscale_hostname)

    table.add_row("", "")
    table.add_row("working dir", str(config.working_dir))
    table.add_row("auth token", config.token[:4] + "*" * min(len(config.token) - 4, 16))

    console.print(Panel(table, title="Server Info", border_style="cyan"))

    # Skip QR code for local-only mode (not useful)
    if config.local_only:
        console.print("\n[dim]QR code disabled for localhost-only mode.[/]")
        console.print("[dim]Use SSH tunnel and manually configure the app with localhost.[/]")
        return

    # QR codes for network modes
    tailscale_ip = config.get_tailscale_ip()

    # Show Tailscale QR first if available (recommended)
    if tailscale_ip:
        console.print("\n[bold green]Scan to connect (Tailscale - Recommended):[/]")
        console.print("-" * 40)
        ts_link = print_qr_code(config, console, "tailscale")
        console.print(f"\n[dim]Link:[/] {ts_link[:60]}...")

    # Then show direct mode
    console.print("\n[bold cyan]Scan to connect (Direct LAN):[/]")
    console.print("-" * 40)
    deep_link = print_qr_code(config, console, "direct")
    console.print(f"\n[dim]Link:[/] {deep_link[:60]}...")
