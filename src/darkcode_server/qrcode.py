"""QR code generation for easy mobile connection."""

import base64
import json
from pathlib import Path
from typing import Optional

import qrcode
from rich.console import Console

from darkcode_server.config import ServerConfig
from darkcode_server.security import CertificateManager


def generate_deep_link(config: ServerConfig, mode: str = "direct", cert_fingerprint: Optional[str] = None) -> str:
    """Generate a deep link URL for the mobile app.

    Args:
        config: Server configuration
        mode: Connection mode (direct, tailscale, ssh)
        cert_fingerprint: TLS certificate SHA256 fingerprint for pinning

    Returns:
        Deep link URL for the mobile app
    """
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

    # Compact payload - single letter keys to minimize QR size
    payload = {
        "n": config.server_name[:20],  # name (truncated)
        "h": host,                      # host
        "p": config.port,               # port
        "t": config.token,              # token
        "m": mode[0],                   # mode (d=direct, t=tailscale, s=ssh)
        "s": 1,                         # secure (TLS required)
    }

    # Add certificate fingerprint for TLS pinning (first 32 chars of SHA256)
    if cert_fingerprint:
        payload["f"] = cert_fingerprint[:32]  # fingerprint (truncated for QR size)

    # Use compact JSON (no spaces)
    b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(',', ':')).encode()
    ).decode().rstrip("=")
    return f"darkcode://s?c={b64}"


def get_cert_fingerprint(config: ServerConfig) -> Optional[str]:
    """Get or generate the server's TLS certificate fingerprint."""
    cert_dir = Path.home() / "darkcode" / ".darkcode" / "certs"
    cert_manager = CertificateManager(cert_dir)

    # Get local IPs for SAN
    local_ips = [ip["address"] for ip in config.get_local_ips()]
    tailscale_ip = config.get_tailscale_ip()
    if tailscale_ip:
        local_ips.append(tailscale_ip)

    return cert_manager.ensure_server_cert(san_ips=local_ips)


def print_qr_code(config: ServerConfig, console: Console, mode: str = "direct", cert_fingerprint: Optional[str] = None):
    """Print a QR code to the terminal."""
    deep_link = generate_deep_link(config, mode, cert_fingerprint)

    qr = qrcode.QRCode(
        version=None,  # Auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)

    # Use half-block characters for compact display (2 rows per line)
    # Upper half block: \u2580, Lower half block: \u2584, Full block: \u2588
    matrix = qr.get_matrix()

    # Pad to even number of rows
    if len(matrix) % 2 == 1:
        matrix.append([False] * len(matrix[0]))

    lines = []
    for i in range(0, len(matrix), 2):
        line = ""
        for j in range(len(matrix[i])):
            top = matrix[i][j]
            bottom = matrix[i + 1][j] if i + 1 < len(matrix) else False

            if top and bottom:
                line += " "  # Both black = white space (inverted)
            elif top:
                line += "\u2584"  # Top black, bottom white = lower half
            elif bottom:
                line += "\u2580"  # Top white, bottom black = upper half
            else:
                line += "\u2588"  # Both white = full block (inverted)
        lines.append(line)

    # Print
    console.print()
    for line in lines:
        console.print(line)
    console.print()

    return deep_link


def generate_qr_png_base64(config: ServerConfig, mode: str = "direct") -> str:
    """Generate QR code as base64-encoded PNG for web display."""
    import io

    deep_link = generate_deep_link(config, mode)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)

    # Generate PNG image
    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return base64.b64encode(buffer.getvalue()).decode()


def print_server_info(config: ServerConfig, console: Console):
    """Print server information with QR codes."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    # Get TLS cert fingerprint (generates cert if needed)
    cert_fingerprint = get_cert_fingerprint(config) if config.tls_enabled else None
    protocol = "wss" if config.tls_enabled else "ws"

    # Server info table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    # Show bind address
    table.add_row("bind", f"{config.bind_host}:{config.port}")

    # Show TLS status
    if config.tls_enabled:
        table.add_row("security", "[green]TLS enabled (wss://)[/]")
        if cert_fingerprint:
            table.add_row("cert", f"[dim]{cert_fingerprint[:16]}...[/]")
    else:
        table.add_row("security", "[red]INSECURE (ws://)[/]")

    if config.local_only:
        # Local-only mode - only localhost
        table.add_row("mode", "[cyan]SSH Tunnel (localhost only)[/]")
    else:
        # Show all available IPs
        ips = config.get_local_ips()
        for ip_info in ips:
            table.add_row(ip_info["name"], f"{protocol}://{ip_info['address']}:{config.port}")

        tailscale_ip = config.get_tailscale_ip()
        tailscale_hostname = config.get_tailscale_hostname()
        if tailscale_ip:
            table.add_row("tailscale", f"{protocol}://{tailscale_ip}:{config.port}")
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
        ts_link = print_qr_code(config, console, "tailscale", cert_fingerprint)
        console.print(f"\n[dim]Link:[/] {ts_link[:60]}...")

    # Then show direct mode
    console.print("\n[bold cyan]Scan to connect (Direct LAN - Secure):[/]")
    console.print("-" * 40)
    deep_link = print_qr_code(config, console, "direct", cert_fingerprint)
    console.print(f"\n[dim]Link:[/] {deep_link[:60]}...")
