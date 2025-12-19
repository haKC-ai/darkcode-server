"""CLI interface for DarkCode Server."""

import asyncio
import os
import platform
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from darkcode_server import __version__
from darkcode_server.config import ServerConfig
from darkcode_server.server import DarkCodeServer

console = Console()


def show_banner():
    """Show the DarkCode banner using hakcer."""
    try:
        from hakcer import show_banner as hakcer_banner, set_theme

        set_theme("synthwave")

        # Try custom banner file locations
        banner_paths = [
            Path("/Users/0xdeadbeef/Desktop/darkcode.txt"),  # Primary custom
            Path.home() / "darkcode" / ".darkcode" / "banner.txt",
            Path(__file__).parent / "assets" / "banner.txt",
        ]

        banner_file = next((p for p in banner_paths if p.exists()), None)

        if banner_file:
            hakcer_banner(
                custom_file=str(banner_file),
                effect_name="rain",
                hold_time=2.0,
            )
        else:
            # Fallback to text
            hakcer_banner(
                text="DARKCODE",
                effect_name="glitch",
                hold_time=1.0,
            )
    except ImportError:
        # Fallback if hakcer not installed
        console.print(
            Panel(
                "[bold magenta]DARKCODE SERVER[/]",
                subtitle=f"v{__version__}",
                border_style="magenta",
            )
        )
    except Exception:
        # Fallback on any error
        console.print(f"[bold magenta]DARKCODE SERVER[/] [dim]v{__version__}[/]")


def interactive_menu():
    """Show an interactive menu for server management."""
    from rich.prompt import IntPrompt

    # Check if first run
    config = ServerConfig.load()
    is_first_run = not (config.config_dir / ".env").exists()

    if is_first_run:
        console.clear()
        show_banner()
        console.print("\n[bold cyan]Welcome to DarkCode Server![/]")
        console.print("[dim]Looks like this is your first time. Let's set things up.[/]\n")
        if Confirm.ask("Run the setup wizard?", default=True):
            setup_wizard_menu()
            return

    while True:
        console.clear()
        show_banner()

        console.print("\n")

        # Menu options
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("", style="bold cyan", width=4)
        table.add_column("", style="white")

        options = [
            ("1", "Start Server", "Launch the WebSocket server"),
            ("2", "Server Status", "Check if server is running"),
            ("3", "Show QR Code", "Display connection QR code"),
            ("4", "Guest Codes", "Create/manage friend access codes"),
            ("5", "Configuration", "View/edit server settings"),
            ("6", "Security", "TLS, tokens, blocked IPs"),
            ("7", "View Logs", "Tail server logs"),
            ("8", "Install Service", "Set up auto-start on boot"),
            ("9", "Setup Wizard", "Re-run initial setup"),
            ("0", "Exit", "Quit the menu"),
        ]

        for num, title, desc in options:
            table.add_row(f"[{num}]", f"{title} [dim]- {desc}[/]")

        console.print(Panel(table, title="Menu", border_style="cyan"))

        try:
            choice = Prompt.ask("\n[cyan]Select option[/]", default="1")
        except (KeyboardInterrupt, EOFError):
            break

        if choice == "0":
            console.print("[dim]Goodbye![/]")
            break
        elif choice == "1":
            menu_start_server()
        elif choice == "2":
            menu_status()
        elif choice == "3":
            menu_qr_code()
        elif choice == "4":
            menu_guest_codes()
        elif choice == "5":
            menu_config()
        elif choice == "6":
            menu_security()
        elif choice == "7":
            menu_logs()
        elif choice == "8":
            menu_install_service()
        elif choice == "9":
            setup_wizard_menu()
        else:
            console.print("[red]Invalid option[/]")

        if choice != "0":
            Prompt.ask("\n[dim]Press Enter to continue[/]")


def setup_wizard_menu():
    """Run setup wizard from menu."""
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(setup_wizard, [], standalone_mode=False)


def menu_guest_codes():
    """Manage guest access codes."""
    config = ServerConfig.load()
    from darkcode_server.security import GuestAccessManager

    guest_mgr = GuestAccessManager(config.config_dir / "guests.db")

    while True:
        console.clear()
        console.print("[bold cyan]Guest Access Codes[/]\n")

        # Show existing codes
        codes = guest_mgr.list_codes()
        if codes:
            table = Table(show_header=True, box=None)
            table.add_column("#", style="dim")
            table.add_column("Code", style="bold cyan")
            table.add_column("Name")
            table.add_column("Status")

            for i, code in enumerate(codes, 1):
                status = "[green]active[/]"
                if code.get("expired"):
                    status = "[yellow]expired[/]"
                elif code.get("max_uses") and code.get("use_count", 0) >= code.get("max_uses"):
                    status = "[yellow]used up[/]"
                table.add_row(str(i), code["code"], code["name"], status)

            console.print(table)
        else:
            console.print("[dim]No guest codes yet.[/]")

        console.print("\n[bold]Options:[/]")
        console.print("  [cyan]c[/] - Create new code")
        console.print("  [cyan]r[/] - Revoke a code")
        console.print("  [cyan]q[/] - Generate QR for a code")
        console.print("  [cyan]b[/] - Back to main menu")

        choice = Prompt.ask("\n[cyan]Select[/]", default="b")

        if choice.lower() == "b":
            break
        elif choice.lower() == "c":
            name = Prompt.ask("Friend's name")
            expires = Prompt.ask("Expires in hours (0=never)", default="24")
            max_uses = Prompt.ask("Max uses (empty=unlimited)", default="")

            result = guest_mgr.create_guest_code(
                name=name,
                expires_hours=int(expires) if expires != "0" else None,
                max_uses=int(max_uses) if max_uses else None,
            )
            console.print(f"\n[green]Created![/] Code: [bold]{result['code']}[/]")
            Prompt.ask("\n[dim]Press Enter to continue[/]")
        elif choice.lower() == "r":
            code = Prompt.ask("Code to revoke")
            if guest_mgr.revoke_code(code):
                console.print(f"[green]Revoked:[/] {code.upper()}")
            else:
                console.print(f"[red]Not found:[/] {code}")
            Prompt.ask("\n[dim]Press Enter to continue[/]")
        elif choice.lower() == "q":
            code = Prompt.ask("Code for QR")
            from click.testing import CliRunner
            runner = CliRunner()
            runner.invoke(guest_qr, [code], standalone_mode=False)
            Prompt.ask("\n[dim]Press Enter to continue[/]")


def menu_security():
    """Security settings menu."""
    config = ServerConfig.load()

    console.clear()
    console.print("[bold cyan]Security Settings[/]\n")

    # Show current status
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("TLS Enabled", "[green]yes[/]" if config.tls_enabled else "[yellow]no[/]")
    table.add_row("mTLS", "[green]yes[/]" if config.mtls_enabled else "[dim]no[/]")
    table.add_row("Device Lock", "[green]yes[/]" if config.device_lock else "[yellow]no[/]")
    table.add_row("Token Rotation", f"{config.token_rotation_days} days" if config.token_rotation_days > 0 else "[dim]disabled[/]")

    console.print(table)

    console.print("\n[bold]Options:[/]")
    console.print("  [cyan]1[/] - Toggle TLS")
    console.print("  [cyan]2[/] - Toggle mTLS")
    console.print("  [cyan]3[/] - Toggle Device Lock")
    console.print("  [cyan]4[/] - Reset Auth Token")
    console.print("  [cyan]5[/] - View Blocked IPs")
    console.print("  [cyan]6[/] - Unbind Device")
    console.print("  [cyan]b[/] - Back")

    choice = Prompt.ask("\n[cyan]Select[/]", default="b")

    if choice == "1":
        config.tls_enabled = not config.tls_enabled
        config.save()
        console.print(f"TLS {'enabled' if config.tls_enabled else 'disabled'}")
    elif choice == "2":
        config.mtls_enabled = not config.mtls_enabled
        if config.mtls_enabled:
            config.tls_enabled = True
        config.save()
        console.print(f"mTLS {'enabled' if config.mtls_enabled else 'disabled'}")
    elif choice == "3":
        config.device_lock = not config.device_lock
        config.save()
        console.print(f"Device lock {'enabled' if config.device_lock else 'disabled'}")
    elif choice == "4":
        menu_reset_token()
    elif choice == "5":
        from click.testing import CliRunner
        runner = CliRunner()
        runner.invoke(security_blocked, [], standalone_mode=False)
    elif choice == "6":
        from click.testing import CliRunner
        runner = CliRunner()
        runner.invoke(device_unbind, [], standalone_mode=False)


def menu_start_server():
    """Start the server from menu."""
    config = ServerConfig.load()

    # Ask for connection mode
    console.print("\n[bold cyan]Connection Mode[/]\n")

    # Check if Tailscale is available
    tailscale_ip = config.get_tailscale_ip()

    mode_table = Table(show_header=False, box=None, padding=(0, 2))
    mode_table.add_column("", style="bold cyan", width=4)
    mode_table.add_column("", style="white")

    mode_table.add_row("[1]", "Direct LAN [dim]- Connect over local network[/]")
    if tailscale_ip:
        mode_table.add_row("[2]", f"Tailscale [green](detected: {tailscale_ip})[/] [dim]- Secure mesh VPN[/]")
    else:
        mode_table.add_row("[2]", "Tailscale [dim]- Secure mesh VPN (not detected)[/]")
    mode_table.add_row("[3]", "SSH Tunnel [dim]- Localhost only, most secure[/]")

    console.print(mode_table)

    mode_choice = Prompt.ask("\n[cyan]Select mode[/]", default="1", choices=["1", "2", "3"])

    if mode_choice == "3":
        config.local_only = True
        console.print("\n[cyan]SSH Tunnel mode - binding to localhost only[/]")
    else:
        config.local_only = False

    console.print(f"\n[cyan]Starting server on port {config.port}...[/]\n")

    try:
        from darkcode_server.qrcode import print_server_info
        print_server_info(config, console)

        # Show connection mode info
        if config.local_only:
            console.print(Panel(
                f"[bold cyan]SSH Tunnel Mode[/] - Localhost only (127.0.0.1:{config.port})\n\n"
                f"To connect remotely, set up an SSH tunnel:\n"
                f"[green]ssh -L {config.port}:localhost:{config.port} user@this-host[/]\n\n"
                f"Then connect to [bold]localhost:{config.port}[/] from the app.",
                title="Connection Mode",
                border_style="cyan",
            ))
        elif tailscale_ip and mode_choice == "2":
            console.print(Panel(
                f"[bold green]Tailscale Mode[/]\n\n"
                f"Tailscale IP: [bold]{tailscale_ip}[/]\n\n"
                f"[dim]Connect using your Tailscale IP for secure remote access.[/]",
                title="Connection Mode: Tailscale",
                border_style="green",
            ))
        elif config.is_exposed:
            console.print(Panel(
                f"[bold yellow]Direct LAN Mode[/] - Server exposed on network\n\n"
                f"[yellow]Warning:[/] Server is accessible from your local network.\n"
                f"Make sure you trust all devices on this network.",
                title="Connection Mode: Direct",
                border_style="yellow",
            ))

        console.print("\n[green]Server running. Press Ctrl+C to stop.[/]\n")

        server = DarkCodeServer(config)
        asyncio.run(_run_server(server))

    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/]")


async def _run_server(server: DarkCodeServer, show_status: bool = True):
    """Run the server until interrupted with live status display."""
    import time
    from datetime import timedelta

    await server.start()
    start_time = time.time()

    try:
        if show_status:
            # Create a live status display that updates periodically
            status_table = Table(show_header=False, box=None, padding=(0, 1))
            status_table.add_column("", style="green", width=2)
            status_table.add_column("", style="dim")

            with Live(console=console, refresh_per_second=1, transient=False) as live:
                while True:
                    # Calculate uptime
                    uptime_secs = int(time.time() - start_time)
                    uptime = str(timedelta(seconds=uptime_secs))

                    # Get session count from server
                    session_count = len(server.sessions) if hasattr(server, 'sessions') else 0
                    state = server.state.value if hasattr(server, 'state') else "running"

                    # Build status display
                    status_text = Text()
                    status_text.append("[*] ", style="bold green")
                    status_text.append("DARKCODE SERVER RUNNING", style="bold green")
                    status_text.append("  |  ", style="dim")
                    status_text.append(f"{uptime}", style="cyan")
                    status_text.append("  |  ", style="dim")
                    status_text.append(f"{session_count} session{'s' if session_count != 1 else ''}", style="yellow")
                    status_text.append("  |  ", style="dim")
                    status_text.append(f"{state}", style="magenta")
                    status_text.append("  |  ", style="dim")
                    status_text.append("Ctrl+C to stop", style="dim italic")

                    live.update(status_text)
                    await asyncio.sleep(1)
        else:
            await asyncio.Future()  # Run forever without status
    finally:
        await server.stop()


def menu_status():
    """Show server status."""
    config = ServerConfig.load()
    console.print("\n[cyan]Checking server status...[/]\n")

    # Check if service is running
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
        )
        if "com.darkcode.server" in result.stdout:
            console.print("[green]Service: Running[/]")
        else:
            console.print("[yellow]Service: Not running[/]")
    else:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "darkcode-server"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print("[green]Service: Running[/]")
        else:
            console.print("[yellow]Service: Not running[/]")

    # Show config info
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Port", str(config.port))
    table.add_row("Working Dir", str(config.working_dir))
    table.add_row("Config Dir", str(config.config_dir))

    console.print(Panel(table, title="Configuration"))


def menu_qr_code():
    """Show QR code."""
    config = ServerConfig.load()
    from darkcode_server.qrcode import print_server_info
    console.print()
    print_server_info(config, console)


def menu_config():
    """View/edit configuration."""
    config = ServerConfig.load()

    console.print("\n[cyan]Current Configuration[/]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Port", str(config.port))
    table.add_row("Working Dir", str(config.working_dir))
    table.add_row("Server Name", config.server_name)
    table.add_row("Token", config.token[:4] + "*" * 16)
    table.add_row("Max Sessions/IP", str(config.max_sessions_per_ip))

    console.print(table)

    if Confirm.ask("\n[cyan]Edit configuration?[/]", default=False):
        new_port = Prompt.ask("Port", default=str(config.port))
        new_dir = Prompt.ask("Working directory", default=str(config.working_dir))
        new_name = Prompt.ask("Server name", default=config.server_name)

        config.port = int(new_port)
        config.working_dir = Path(new_dir)
        config.server_name = new_name
        config.save()

        console.print("\n[green]Configuration saved![/]")


def menu_reset_token():
    """Generate a new auth token."""
    if Confirm.ask("\n[yellow]Generate new auth token? Current connections will be invalidated.[/]"):
        config = ServerConfig.load()
        config.token = secrets.token_urlsafe(24)
        config.save()

        console.print(f"\n[green]New token:[/] {config.token}")
        console.print("[dim]Save this token - you'll need it to connect.[/]")


def menu_logs():
    """View server logs."""
    config = ServerConfig.load()
    log_file = config.log_dir / "server.log"

    if not log_file.exists():
        console.print("\n[yellow]No logs found.[/]")
        return

    console.print(f"\n[cyan]Tailing {log_file}...[/]")
    console.print("[dim]Press Ctrl+C to stop[/]\n")

    try:
        subprocess.run(["tail", "-f", str(log_file)])
    except KeyboardInterrupt:
        pass


def menu_install_service():
    """Install as system service."""
    config = ServerConfig.load()

    console.print("\n[cyan]Installing as system service...[/]\n")

    if platform.system() == "Darwin":
        _install_launchd(config)
    else:
        _install_systemd(config)


def _install_launchd(config: ServerConfig):
    """Install launchd service on macOS."""
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.darkcode.server.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    python_path = sys.executable
    module_path = "darkcode_server.cli"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.darkcode.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>{module_path}</string>
        <string>start</string>
        <string>--no-banner</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{config.working_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{config.log_dir}/server.log</string>
    <key>StandardErrorPath</key>
    <string>{config.log_dir}/error.log</string>
</dict>
</plist>
"""

    config.log_dir.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)

    # Unload if exists, then load
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True)

    if result.returncode == 0:
        console.print("[green]Service installed and started![/]")
        console.print(f"[dim]Plist: {plist_path}[/]")
    else:
        console.print(f"[red]Failed to install service: {result.stderr.decode()}[/]")


def _install_systemd(config: ServerConfig):
    """Install systemd service on Linux."""
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)

    service_path = service_dir / "darkcode-server.service"
    python_path = sys.executable

    service_content = f"""[Unit]
Description=DarkCode Server
After=network.target

[Service]
Type=simple
ExecStart={python_path} -m darkcode_server.cli start --no-banner
WorkingDirectory={config.working_dir}
Restart=on-failure
RestartSec=5
StandardOutput=append:{config.log_dir}/server.log
StandardError=append:{config.log_dir}/error.log

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
"""

    config.log_dir.mkdir(parents=True, exist_ok=True)
    service_path.write_text(service_content)

    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", "darkcode-server"])
    result = subprocess.run(["systemctl", "--user", "start", "darkcode-server"])

    if result.returncode == 0:
        console.print("[green]Service installed and started![/]")
        console.print(f"[dim]Service file: {service_path}[/]")
    else:
        console.print("[red]Failed to start service[/]")


def menu_uninstall():
    """Uninstall the server."""
    if not Confirm.ask("\n[red]Uninstall DarkCode Server? This will remove all data.[/]"):
        return

    config = ServerConfig.load()

    # Stop and remove service
    if platform.system() == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.darkcode.server.plist"
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        plist_path.unlink(missing_ok=True)
    else:
        subprocess.run(["systemctl", "--user", "stop", "darkcode-server"], capture_output=True)
        subprocess.run(["systemctl", "--user", "disable", "darkcode-server"], capture_output=True)
        service_path = Path.home() / ".config" / "systemd" / "user" / "darkcode-server.service"
        service_path.unlink(missing_ok=True)

    # Remove config directory
    import shutil
    if config.config_dir.exists():
        shutil.rmtree(config.config_dir)

    console.print("\n[green]Uninstalled successfully![/]")
    console.print("[dim]Run 'pip uninstall darkcode-server' to remove the package.[/]")


def prompt_install_tailscale():
    """Prompt user to install Tailscale."""
    console.print("\n[bold yellow]Tailscale is not installed[/]\n")
    console.print("Tailscale provides a secure mesh VPN that makes connecting")
    console.print("from your phone easy and secure, even outside your home network.\n")

    console.print("[bold cyan]Benefits:[/]")
    console.print("  • Secure encrypted connection from anywhere")
    console.print("  • No port forwarding required")
    console.print("  • Works across networks (cellular, coffee shop wifi, etc.)")
    console.print("  • Free for personal use\n")

    system = platform.system()

    if system == "Darwin":
        console.print("[bold]Install on macOS:[/]")
        console.print("  brew install tailscale")
        console.print("  [dim]or download from https://tailscale.com/download/mac[/]\n")

        if Confirm.ask("Install with Homebrew now?", default=True):
            console.print("\n[dim]Installing Tailscale...[/]")
            result = subprocess.run(["brew", "install", "tailscale"], capture_output=False)
            if result.returncode == 0:
                console.print("\n[green]Tailscale installed![/]")
                console.print("Run [bold]tailscale up[/] to connect to your tailnet.")
            else:
                console.print("\n[red]Installation failed. Try installing manually.[/]")

    elif system == "Linux":
        console.print("[bold]Install on Linux:[/]")
        console.print("  curl -fsSL https://tailscale.com/install.sh | sh")
        console.print("  [dim]or see https://tailscale.com/download/linux[/]\n")

    else:
        console.print(f"[bold]Install on {system}:[/]")
        console.print("  Visit https://tailscale.com/download\n")

    console.print("[dim]After installing, run 'tailscale up' to connect.[/]")
    console.print("[dim]Then restart darkcode and select Tailscale mode.[/]\n")

    Prompt.ask("Press Enter to continue")


# Click CLI commands
@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Show version")
@click.option("--classic", is_flag=True, help="Use classic text menu instead of interactive dialogs")
@click.pass_context
def main(ctx, version, classic):
    """DarkCode Server - Remote Claude Code from your phone."""
    if version:
        console.print(f"darkcode-server v{__version__}")
        return

    if ctx.invoked_subcommand is None:
        if classic:
            # Use old menu if explicitly requested
            show_banner()
            interactive_menu()
        else:
            # Default to arrow-key navigation menu using prompt_toolkit
            try:
                from darkcode_server.prompt_ui import run_interactive_menu
                result = run_interactive_menu()
                if result:
                    action, data = result
                    if action == "start":
                        # data is a dict with mode, port, working_dir, no_web, save
                        config = ServerConfig.load()
                        local_only = data.get("mode") == "ssh"
                        port = data.get("port", config.port)
                        working_dir = data.get("working_dir", str(config.working_dir))
                        no_web = data.get("no_web", False)
                        if data.get("save"):
                            config.port = port
                            config.working_dir = Path(working_dir)
                            config.save()
                        ctx.invoke(start, port=port, working_dir=working_dir, local_only=local_only, no_web=no_web, no_banner=True)
                    elif action == "daemon_foreground":
                        ctx.invoke(daemon, detach=False)
                    elif action == "daemon_background":
                        ctx.invoke(daemon, detach=True)
                    elif action == "daemon_stop":
                        ctx.invoke(stop)
                    elif action == "setup":
                        setup_wizard_menu()
                    elif action == "install":
                        ctx.invoke(install)
                    elif action == "uninstall":
                        ctx.invoke(uninstall)
                    elif action == "rotate_token":
                        ctx.invoke(rotate_token)
                    elif action == "client_cert":
                        device_id = data
                        ctx.invoke(client_cert, device_id=device_id)
            except ImportError as e:
                console.print(f"[yellow]prompt_toolkit not installed. Falling back to classic menu.[/]")
                console.print(f"[dim]Install with: pip install prompt_toolkit[/]")
                show_banner()
                interactive_menu()
            except Exception as e:
                import traceback
                console.print(f"[yellow]Menu error: {e}[/]")
                console.print(f"[dim]{traceback.format_exc()}[/]")
                show_banner()
                interactive_menu()


@main.command()
@click.option("--port", "-p", type=int, envvar="DARKCODE_PORT", help="Server port (default: 3100, env: DARKCODE_PORT)")
@click.option("--token", "-t", envvar="DARKCODE_TOKEN", help="Auth token (env: DARKCODE_TOKEN)")
@click.option("--working-dir", "-d", type=click.Path(exists=True), envvar="DARKCODE_WORKING_DIR", help="Working directory for Claude (env: DARKCODE_WORKING_DIR)")
@click.option("--browse-dir", "-b", type=click.Path(exists=True), envvar="DARKCODE_BROWSE_DIR", help="Default directory for app file browser (env: DARKCODE_BROWSE_DIR)")
@click.option("--name", "-n", envvar="DARKCODE_SERVER_NAME", help="Server display name")
@click.option("--local-only", "-l", is_flag=True, envvar="DARKCODE_LOCAL_ONLY", help="Only accept localhost connections (use with SSH tunnel)")
@click.option("--no-banner", is_flag=True, help="Skip banner animation")
@click.option("--no-web", is_flag=True, envvar="DARKCODE_NO_WEB", help="Disable web admin dashboard")
@click.option("--save", "-s", is_flag=True, help="Save options to config file")
def start(port, token, working_dir, browse_dir, name, local_only, no_banner, no_web, save):
    """Start the DarkCode server.

    CONNECTION MODES:

    1. Direct (LAN) - Default, connect over local network:

       darkcode start

    2. Tailscale - Secure mesh VPN (recommended for remote):

       darkcode start
       (Connect using your Tailscale IP shown in output)

    3. SSH Tunnel - Most secure, localhost only:

       darkcode start --local-only
       (Then SSH tunnel: ssh -L 3100:localhost:3100 user@host)

    EXAMPLES:

      darkcode start                      # Use saved config

      darkcode start -p 8080              # Custom port

      darkcode start --local-only         # Localhost only (for SSH tunnel)

      darkcode start -p 8080 -s           # Save port to config

    Environment variables (DARKCODE_PORT, DARKCODE_TOKEN, etc.) also work.
    """
    if not no_banner:
        show_banner()

    # Check if first run (no config exists)
    # Check both new and legacy config locations
    new_config_file = Path.home() / "darkcode" / ".darkcode" / ".env"
    legacy_config_file = Path.home() / ".darkcode" / ".env"
    config_file = new_config_file if new_config_file.exists() else legacy_config_file
    first_run = not config_file.exists()

    config = ServerConfig.load()

    # Override with CLI options
    if port:
        config.port = port
    if token:
        config.token = token
    if working_dir:
        config.working_dir = Path(working_dir)
    if browse_dir:
        config.browse_dir = Path(browse_dir)
    if name:
        config.server_name = name
    if local_only:
        config.local_only = True
    if no_web:
        config.web_admin_disabled = True

    # Auto-save on first run or if requested
    if first_run or save:
        config.save()
        if first_run:
            console.print(Panel(
                f"[bold green]First run - config saved![/]\n\n"
                f"[cyan]Auth Token:[/] [bold]{config.token}[/]\n\n"
                f"[dim]Save this token - you need it to connect from the app.\n"
                f"Config: {config_file}[/]",
                title="Welcome to DarkCode",
                border_style="green",
            ))
            console.print()
        else:
            console.print("[green]Configuration saved![/]\n")

    from darkcode_server.qrcode import print_server_info
    print_server_info(config, console)

    # Show connection mode and security info
    if config.local_only:
        console.print(Panel(
            f"[bold cyan]SSH Tunnel Mode[/] - Localhost only (127.0.0.1:{config.port})\n\n"
            f"To connect remotely, set up an SSH tunnel:\n"
            f"[green]ssh -L {config.port}:localhost:{config.port} user@this-host[/]\n\n"
            f"Then connect to [bold]localhost:{config.port}[/] from the app.",
            title="Connection Mode",
            border_style="cyan",
        ))
    else:
        # Check for Tailscale
        tailscale_ip = config.get_tailscale_ip()
        tailscale_hostname = config.get_tailscale_hostname()

        if tailscale_ip:
            console.print(Panel(
                f"[bold green]Tailscale Detected[/] - Secure mesh VPN available\n\n"
                f"Tailscale IP: [bold]{tailscale_ip}[/]\n"
                + (f"Hostname: [bold]{tailscale_hostname}[/]\n" if tailscale_hostname else "")
                + f"\n[dim]Connect using Tailscale IP for secure remote access.[/]",
                title="Connection Mode: Tailscale (Recommended)",
                border_style="green",
            ))
        elif config.is_exposed:
            console.print(Panel(
                f"[bold yellow]Direct LAN Mode[/] - Server exposed on network\n\n"
                f"[yellow]Warning:[/] Server is accessible from your local network.\n"
                f"Make sure you trust all devices on this network.\n\n"
                f"[dim]For remote access, consider:\n"
                f"  - Tailscale: Install and run 'tailscale up'\n"
                f"  - SSH Tunnel: Run with --local-only flag[/]",
                title="Connection Mode: Direct",
                border_style="yellow",
            ))

    console.print(f"\n[green]Server listening on {config.bind_host}:{config.port}[/]")

    # Show admin URL and PIN (unless disabled)
    if not config.web_admin_disabled:
        local_ips = config.get_local_ips()
        local_ip = local_ips[0]["address"] if local_ips else "127.0.0.1"
        protocol = "https" if config.tls_enabled else "http"
        console.print(f"[cyan]Web Admin:[/] {protocol}://{local_ip}:{config.port}/admin")

        # Get and display web PIN
        try:
            from darkcode_server.web_admin import WebAdminHandler
            web_pin = WebAdminHandler.get_web_pin()
            console.print(f"[cyan]Web PIN:[/] [bold yellow]{web_pin}[/]")
        except ImportError:
            pass
    else:
        console.print("[dim]Web Admin: disabled (--no-web)[/]")

    console.print("[dim]Press Ctrl+C to stop[/]\n")

    server = DarkCodeServer(config)

    try:
        asyncio.run(_run_server(server))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/]")


@main.command()
def status():
    """Show server status."""
    menu_status()


@main.command()
def qr():
    """Show connection QR code."""
    show_banner()
    menu_qr_code()


@main.command()
def config():
    """View/edit configuration."""
    menu_config()


@main.command()
def token():
    """Show current auth token."""
    cfg = ServerConfig.load()
    console.print(f"[cyan]Auth Token:[/] {cfg.token}")


@main.command()
def pin():
    """Show web admin PIN for running server.

    If a DarkCode server is running (daemon or foreground),
    this shows the PIN needed to access the web admin interface.
    """
    from darkcode_server.web_admin import WebAdminHandler

    # Try to load PIN from file (saved by running server)
    pin = WebAdminHandler.load_pin_from_file()

    if pin:
        cfg = ServerConfig.load()
        local_ips = cfg.get_local_ips()
        local_ip = local_ips[0]['address'] if local_ips else '127.0.0.1'
        protocol = 'https' if cfg.tls_enabled else 'http'

        console.print(f"\n[bold cyan]Web Admin PIN:[/] [bold yellow]{pin}[/]\n")
        console.print(f"[dim]URL: {protocol}://{local_ip}:{cfg.port}/admin[/]\n")
    else:
        console.print("[yellow]No running server found.[/]")
        console.print("[dim]Start the server with 'darkcode start' or 'darkcode daemon' first.[/]")


@main.command("token-reset")
def token_reset():
    """Generate new auth token."""
    menu_reset_token()


@main.command()
def logs():
    """Tail server logs."""
    menu_logs()


@main.command()
def install():
    """Install as system service."""
    show_banner()
    menu_install_service()


@main.command()
def uninstall():
    """Uninstall server completely."""
    menu_uninstall()


@main.command()
@click.option("--port", "-p", type=int, default=3100, help="Server port")
@click.option("--working-dir", "-d", type=click.Path(), help="Working directory")
@click.option("--name", "-n", help="Server name")
def init(port, working_dir, name):
    """Initialize server configuration."""
    show_banner()

    console.print("\n[cyan]DarkCode Server Setup[/]\n")

    # Get settings
    if not port:
        port = int(Prompt.ask("Port", default="3100"))
    if not working_dir:
        working_dir = Prompt.ask("Working directory", default=str(Path.cwd()))
    if not name:
        name = Prompt.ask("Server name", default=platform.node())

    config = ServerConfig(
        port=port,
        working_dir=Path(working_dir),
        server_name=name,
    )
    config.save()

    console.print("\n[green]Configuration saved![/]\n")
    console.print(f"[cyan]Auth Token:[/] {config.token}")
    console.print("[dim]Save this token - you'll need it to connect from the app.[/]")
    console.print(f"\n[dim]Config saved to: {config.config_dir / '.env'}[/]")


@main.command("daemon")
@click.option("--background", "-b", is_flag=True, help="Run in background (detach from terminal)")
def daemon_start(background):
    """Start server as daemon (persists after terminal close).

    The daemon will:
    - Continue running after you close the terminal
    - Log all connections to ~/.darkcode/logs/
    - Lock to the first device that connects (device binding)
    - Sleep after idle timeout, only allowing bound device to wake

    Examples:

      darkcode daemon              # Run in foreground with logging

      darkcode daemon -b           # Run in background (detach)

      darkcode stop                # Stop the background daemon
    """
    from darkcode_server.daemon import DarkCodeDaemon, run_daemon

    config = ServerConfig.load()

    # Check if already running
    existing = DarkCodeDaemon.get_running_pid(config)
    if existing:
        console.print(f"[yellow]Daemon already running with PID {existing}[/]")
        console.print("[dim]Use 'darkcode stop' to stop it first.[/]")
        return

    if not background:
        show_banner()
        console.print(Panel(
            f"[bold green]Daemon Mode[/]\n\n"
            f"Port: [bold]{config.port}[/]\n"
            f"Device Lock: [bold]{'enabled' if config.device_lock else 'disabled'}[/]\n"
            f"Idle Timeout: [bold]{config.idle_timeout}s[/]\n\n"
            f"[dim]Logs: {config.log_dir}/[/]",
            title="DarkCode Daemon",
            border_style="green",
        ))
        console.print("\n[green]Starting daemon...[/]")
        console.print("[dim]Press Ctrl+C to stop[/]\n")

    try:
        run_daemon(config, background=background)
    except KeyboardInterrupt:
        console.print("\n[yellow]Daemon stopped.[/]")
    except RuntimeError as e:
        console.print(f"[red]Error: {e}[/]")


@main.command("stop")
def daemon_stop():
    """Stop running daemon."""
    from darkcode_server.daemon import DarkCodeDaemon

    config = ServerConfig.load()
    pid = DarkCodeDaemon.get_running_pid(config)

    if not pid:
        console.print("[yellow]No daemon running.[/]")
        return

    console.print(f"[cyan]Stopping daemon (PID {pid})...[/]")

    if DarkCodeDaemon.stop_running(config):
        console.print("[green]Daemon stopped.[/]")
    else:
        console.print("[red]Failed to stop daemon.[/]")


@main.command("unbind")
def device_unbind():
    """Unbind the server from its locked device.

    This allows a new device to connect and become the bound device.
    Use this if you need to switch to a different phone.
    """
    config = ServerConfig.load()

    if not config.bound_device_id:
        console.print("[yellow]No device is currently bound.[/]")
        return

    if not Confirm.ask("[yellow]Unbind current device? A new device will be able to connect and lock the server.[/]"):
        return

    config.bound_device_id = None
    config.save()

    console.print("[green]Device unbound.[/]")
    console.print("[dim]The next device to authenticate will become the new bound device.[/]")

    # If daemon is running, it will pick up the change on next connection


@main.group()
def security():
    """Security management commands."""
    pass


@security.command("status")
def security_status():
    """Show security status and bound device info."""
    config = ServerConfig.load()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    table.add_row("Device Lock", "[green]enabled[/]" if config.device_lock else "[yellow]disabled[/]")
    table.add_row("Bound Device", config.bound_device_id[:12] + "..." if config.bound_device_id else "[dim]none[/]")
    table.add_row("Idle Timeout", f"{config.idle_timeout}s" if config.idle_timeout > 0 else "[dim]disabled[/]")
    table.add_row("Local Only", "[green]yes[/]" if config.local_only else "[yellow]no[/]")
    table.add_row("Rate Limit", f"{config.rate_limit_attempts} attempts / {config.rate_limit_window}s")
    table.add_row("Max Sessions/IP", str(config.max_sessions_per_ip))

    # TLS status
    table.add_row("", "")  # Spacer
    table.add_row("[bold]TLS/Security[/]", "")
    table.add_row("TLS Enabled", "[green]yes (wss://)[/]" if config.tls_enabled else "[yellow]no (ws://)[/]")
    table.add_row("mTLS", "[green]enabled[/]" if config.mtls_enabled else "[dim]disabled[/]")
    table.add_row("Token Rotation", f"{config.token_rotation_days} days" if config.token_rotation_days > 0 else "[dim]disabled[/]")

    # Check for certs
    cert_dir = config.config_dir / "certs"
    server_cert = cert_dir / "server.crt"
    ca_cert = cert_dir / "ca.crt"
    table.add_row("Server Cert", "[green]exists[/]" if server_cert.exists() else "[dim]not generated[/]")
    table.add_row("CA Cert (mTLS)", "[green]exists[/]" if ca_cert.exists() else "[dim]not generated[/]")

    console.print(Panel(table, title="Security Status", border_style="cyan"))

    # Check for running daemon
    from darkcode_server.daemon import DarkCodeDaemon
    pid = DarkCodeDaemon.get_running_pid(config)
    if pid:
        console.print(f"\n[green]Daemon running[/] (PID {pid})")
    else:
        console.print("\n[dim]Daemon not running[/]")

    # Show security database stats
    from darkcode_server.security import PersistentRateLimiter, TokenManager
    db_path = config.config_dir / "security.db"
    if db_path.exists():
        rate_limiter = PersistentRateLimiter(db_path)
        stats = rate_limiter.get_stats()
        console.print(f"\n[cyan]Rate Limiter:[/] {stats['total_attempts']} attempts, {stats['failed_attempts']} failed, {stats['blocked_count']} blocked")

    token_db = config.config_dir / "tokens.db"
    if token_db.exists():
        token_mgr = TokenManager(token_db)
        token_info = token_mgr.get_token_info()
        if token_info and token_info.get("expires_in_days") is not None:
            console.print(f"[cyan]Token:[/] expires in {token_info['expires_in_days']:.1f} days")

    # Show log locations
    console.print(f"\n[cyan]Connection logs:[/] {config.log_dir / 'connections.log'}")
    console.print(f"[cyan]Server logs:[/] {config.log_dir / 'server.log'}")


@security.command("tls")
@click.option("--enable/--disable", default=None, help="Enable or disable TLS")
@click.option("--mtls/--no-mtls", default=None, help="Enable or disable mTLS (client certificates)")
@click.option("--regenerate", is_flag=True, help="Regenerate server certificate")
def security_tls(enable, mtls, regenerate):
    """Configure TLS/SSL for secure WebSocket (wss://).

    TLS encrypts all traffic between the app and server.
    mTLS additionally requires client certificates for device authentication.

    Examples:

      darkcode security tls --enable          # Enable TLS

      darkcode security tls --enable --mtls   # Enable TLS + mTLS

      darkcode security tls --regenerate      # Regenerate certificates
    """
    config = ServerConfig.load()

    if enable is not None:
        config.tls_enabled = enable
        config.save()
        if enable:
            console.print("[green]TLS enabled[/] - Server will use wss://")
            # Generate cert if needed
            from darkcode_server.security import CertificateManager
            cert_mgr = CertificateManager(config.config_dir / "certs")
            if not cert_mgr.server_cert_path.exists() or regenerate:
                local_ips = [ip["address"] for ip in config.get_local_ips()]
                tailscale_ip = config.get_tailscale_ip()
                if tailscale_ip:
                    local_ips.append(tailscale_ip)
                cert_mgr.generate_server_cert(hostname=config.server_name, san_ips=local_ips)
                console.print(f"[green]Generated server certificate[/] at {cert_mgr.server_cert_path}")
        else:
            console.print("[yellow]TLS disabled[/] - Server will use ws:// (unencrypted)")

    if mtls is not None:
        config.mtls_enabled = mtls
        config.save()
        if mtls:
            config.tls_enabled = True  # mTLS requires TLS
            config.save()
            console.print("[green]mTLS enabled[/] - Clients must present certificates")
            # Generate CA if needed
            from darkcode_server.security import CertificateManager
            cert_mgr = CertificateManager(config.config_dir / "certs")
            if not cert_mgr.ca_cert_path.exists():
                cert_mgr.generate_ca()
                console.print(f"[green]Generated CA certificate[/] at {cert_mgr.ca_cert_path}")
        else:
            console.print("[yellow]mTLS disabled[/] - Token-only authentication")

    if regenerate and config.tls_enabled:
        from darkcode_server.security import CertificateManager
        cert_mgr = CertificateManager(config.config_dir / "certs")
        local_ips = [ip["address"] for ip in config.get_local_ips()]
        tailscale_ip = config.get_tailscale_ip()
        if tailscale_ip:
            local_ips.append(tailscale_ip)
        cert_mgr.generate_server_cert(hostname=config.server_name, san_ips=local_ips)
        console.print(f"[green]Regenerated server certificate[/]")

    # Show current status
    if enable is None and mtls is None and not regenerate:
        console.print(f"TLS: [{'green]enabled' if config.tls_enabled else 'yellow]disabled'}[/]")
        console.print(f"mTLS: [{'green]enabled' if config.mtls_enabled else 'dim]disabled'}[/]")
        console.print("\nUse --enable/--disable and --mtls/--no-mtls to configure.")


@security.command("client-cert")
@click.argument("device_id")
@click.option("--show-qr", is_flag=True, help="Display QR code for easy mobile import")
def security_client_cert(device_id, show_qr):
    """Generate a client certificate for mTLS device binding.

    This creates a certificate that the mobile app uses to authenticate.
    The certificate is tied to a specific device ID.

    Example:

      darkcode security client-cert my-phone

      darkcode security client-cert my-phone --show-qr
    """
    config = ServerConfig.load()

    if not config.tls_enabled:
        console.print("[yellow]Warning:[/] TLS is not enabled. Enable it with 'darkcode security tls --enable'")

    from darkcode_server.security import CertificateManager
    cert_mgr = CertificateManager(config.config_dir / "certs")

    console.print(f"[cyan]Generating client certificate for device:[/] {device_id}")

    cert_path, key_path, p12_path = cert_mgr.generate_client_cert(device_id)
    password_file = cert_mgr.client_certs_dir / f"{device_id}.password"
    p12_password = password_file.read_text() if password_file.exists() else "unknown"

    console.print(f"\n[green]Certificate generated![/]\n")
    console.print(f"[cyan]Certificate:[/] {cert_path}")
    console.print(f"[cyan]Private Key:[/] {key_path}")
    console.print(f"[cyan]PKCS12 (for mobile):[/] {p12_path}")
    console.print(f"[cyan]PKCS12 Password:[/] {p12_password}")

    console.print(Panel(
        f"To import on Android:\n\n"
        f"1. Transfer [bold]{p12_path.name}[/] to your device\n"
        f"2. Open Settings > Security > Install from storage\n"
        f"3. Select the .p12 file\n"
        f"4. Enter password: [bold]{p12_password}[/]\n"
        f"5. The DarkCode app will use this certificate automatically",
        title="Import Instructions",
        border_style="cyan",
    ))

    if show_qr:
        try:
            import qrcode
            import base64

            # Create QR with p12 path and password (for easy copy)
            qr_data = f"darkcode://cert?path={p12_path}&password={p12_password}"
            qr = qrcode.QRCode(box_size=1, border=1)
            qr.add_data(qr_data)
            qr.make(fit=True)

            console.print("\n[cyan]Certificate Info QR Code:[/]")
            # Print QR as text
            matrix = qr.get_matrix()
            for row in matrix:
                line = "".join("██" if cell else "  " for cell in row)
                console.print(line)
        except Exception as e:
            console.print(f"[yellow]QR generation failed: {e}[/]")


@security.command("blocked")
@click.option("--unblock", help="Unblock a specific IP or device ID")
def security_blocked(unblock):
    """View and manage blocked IPs/devices."""
    config = ServerConfig.load()
    from darkcode_server.security import PersistentRateLimiter

    db_path = config.config_dir / "security.db"
    if not db_path.exists():
        console.print("[dim]No security database yet.[/]")
        return

    rate_limiter = PersistentRateLimiter(db_path)

    if unblock:
        # Try to unblock as both IP and device
        rate_limiter.unblock(unblock, "ip")
        rate_limiter.unblock(unblock, "device")
        console.print(f"[green]Unblocked:[/] {unblock}")
        return

    blocked = rate_limiter.get_blocked()
    if not blocked:
        console.print("[green]No blocked IPs or devices.[/]")
        return

    table = Table(title="Blocked IPs/Devices")
    table.add_column("Identifier", style="red")
    table.add_column("Type")
    table.add_column("Blocked At")
    table.add_column("Until")
    table.add_column("Reason")

    from datetime import datetime
    for b in blocked:
        blocked_at = datetime.fromtimestamp(b["blocked_at"]).strftime("%Y-%m-%d %H:%M")
        until = datetime.fromtimestamp(b["blocked_until"]).strftime("%Y-%m-%d %H:%M") if b["blocked_until"] else "permanent"
        table.add_row(b["identifier"][:20], b["identifier_type"], blocked_at, until, b["reason"] or "-")

    console.print(table)
    console.print("\n[dim]Use --unblock <identifier> to unblock[/]")


@security.command("rotate-token")
@click.option("--force", is_flag=True, help="Force rotation even if not due")
def security_rotate_token(force):
    """Manually rotate the auth token.

    When token rotation is enabled, old tokens remain valid for the
    grace period (default 24 hours) after rotation.
    """
    config = ServerConfig.load()

    if config.token_rotation_days <= 0:
        console.print("[yellow]Token rotation is disabled.[/]")
        console.print("[dim]Enable it by setting DARKCODE_TOKEN_ROTATION_DAYS in your config.[/]")
        return

    from darkcode_server.security import TokenManager
    token_mgr = TokenManager(
        db_path=config.config_dir / "tokens.db",
        rotation_days=config.token_rotation_days,
        grace_hours=config.token_grace_hours,
    )

    if not force and not token_mgr.should_rotate():
        info = token_mgr.get_token_info()
        if info:
            console.print(f"[yellow]Rotation not due yet.[/] Token expires in {info.get('expires_in_days', 0):.1f} days.")
            console.print("[dim]Use --force to rotate anyway.[/]")
        return

    new_token = token_mgr.rotate()
    config.token = new_token
    config.save()

    console.print("[green]Token rotated![/]")
    console.print(f"\n[cyan]New Token:[/] {new_token}")
    console.print(f"\n[dim]Old tokens valid for {config.token_grace_hours} hours.[/]")


# Guest access commands
@main.group()
def guest():
    """Manage guest access codes for friends."""
    pass


@guest.command("create")
@click.argument("name")
@click.option("--expires", "-e", type=int, default=24, help="Hours until expiration (0=never)")
@click.option("--max-uses", "-m", type=int, default=None, help="Max number of uses")
@click.option("--read-only", "-r", is_flag=True, help="Read-only access (no commands)")
@click.option("--code", "-c", help="Use custom code instead of generating")
def guest_create(name, expires, max_uses, read_only, code):
    """Create a guest access code for a friend.

    Examples:

      darkcode guest create "John's phone"

      darkcode guest create "Demo" --expires 1 --max-uses 3

      darkcode guest create "Read Only Demo" --read-only

      darkcode guest create "Party Code" --code PARTY1
    """
    config = ServerConfig.load()
    from darkcode_server.security import GuestAccessManager

    guest_mgr = GuestAccessManager(config.config_dir / "guests.db")

    try:
        result = guest_mgr.create_guest_code(
            name=name,
            permission_level="read_only" if read_only else "full",
            expires_hours=expires if expires > 0 else None,
            max_uses=max_uses,
            custom_code=code.upper() if code else None,
        )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/]")
        return

    expires_str = f"in {result['expires_in_hours']}h" if result['expires_in_hours'] else "never"
    max_uses_str = str(result['max_uses']) if result['max_uses'] else "unlimited"
    console.print(Panel(
        f"[bold green]Guest Code Created![/]\n\n"
        f"[cyan]Code:[/] [bold]{result['code']}[/]\n"
        f"[cyan]Name:[/] {result['name']}\n"
        f"[cyan]Permission:[/] {result['permission_level']}\n"
        f"[cyan]Expires:[/] {expires_str}\n"
        f"[cyan]Max Uses:[/] {max_uses_str}\n\n"
        "[dim]Share this code with your friend. They enter it instead of the auth token.[/]",
        title="Guest Access",
        border_style="green",
    ))

    # Show QR code option
    console.print("\n[dim]To generate a connection QR for this guest:[/]")
    console.print(f"  darkcode guest qr {result['code']}")


@guest.command("list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Include revoked/expired codes")
def guest_list(show_all):
    """List all guest access codes."""
    config = ServerConfig.load()
    from darkcode_server.security import GuestAccessManager

    guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
    codes = guest_mgr.list_codes(include_inactive=show_all)

    if not codes:
        console.print("[dim]No guest codes found.[/]")
        console.print("\n[cyan]Create one with:[/] darkcode guest create \"Friend's name\"")
        return

    table = Table(title="Guest Access Codes")
    table.add_column("Code", style="bold cyan")
    table.add_column("Name")
    table.add_column("Permission")
    table.add_column("Expires")
    table.add_column("Uses")
    table.add_column("Status")

    for code in codes:
        status = "[green]active[/]"
        if not code.get("is_active"):
            status = "[red]revoked[/]"
        elif code.get("expired"):
            status = "[yellow]expired[/]"
        elif code.get("max_uses") and code.get("use_count", 0) >= code.get("max_uses"):
            status = "[yellow]used up[/]"

        expires = "never"
        if code.get("expires_in_hours") is not None:
            if code.get("expires_in_hours") < 1:
                expires = f"{int(code['expires_in_hours'] * 60)}m"
            else:
                expires = f"{code['expires_in_hours']:.1f}h"

        uses = f"{code.get('use_count', 0)}"
        if code.get("max_uses"):
            uses += f"/{code['max_uses']}"

        table.add_row(
            code["code"],
            code["name"],
            code["permission_level"],
            expires,
            uses,
            status,
        )

    console.print(table)


@guest.command("revoke")
@click.argument("code")
def guest_revoke(code):
    """Revoke a guest access code."""
    config = ServerConfig.load()
    from darkcode_server.security import GuestAccessManager

    guest_mgr = GuestAccessManager(config.config_dir / "guests.db")

    if guest_mgr.revoke_code(code):
        console.print(f"[green]Revoked guest code:[/] {code.upper()}")
    else:
        console.print(f"[red]Code not found:[/] {code.upper()}")


@guest.command("qr")
@click.argument("code")
def guest_qr(code):
    """Generate QR code for guest access."""
    config = ServerConfig.load()
    from darkcode_server.security import GuestAccessManager

    guest_mgr = GuestAccessManager(config.config_dir / "guests.db")
    valid, info = guest_mgr.verify_code(code)

    if not valid:
        console.print(f"[red]Invalid or expired code:[/] {code.upper()}")
        return

    # Get connection info
    tailscale_ip = config.get_tailscale_ip()
    local_ips = config.get_local_ips()

    # Build QR data with guest code
    import json
    import base64

    qr_config = {
        "host": tailscale_ip or (local_ips[0]["address"] if local_ips else "localhost"),
        "port": config.port,
        "name": config.server_name,
        "guest_code": code.upper(),
        "guest_name": info.get("name", ""),
        "tls": config.tls_enabled,
    }

    deep_link = f"darkcode://connect?config={base64.urlsafe_b64encode(json.dumps(qr_config).encode()).decode()}"

    console.print(f"\n[bold cyan]Guest QR Code for:[/] {info.get('name', code.upper())}")
    console.print("-" * 40)

    try:
        import qrcode
        qr = qrcode.QRCode(box_size=1, border=1)
        qr.add_data(deep_link)
        qr.make(fit=True)

        matrix = qr.get_matrix()
        for row in matrix:
            line = "".join("██" if cell else "  " for cell in row)
            console.print(line)
    except Exception as e:
        console.print(f"[yellow]QR generation failed: {e}[/]")

    console.print(f"\n[dim]Guest code:[/] [bold]{code.upper()}[/]")
    console.print(f"[dim]Expires:[/] {info.get('expires_in_hours', 'never')}h" if info.get("expires_at") else "[dim]Expires:[/] never")


# Setup wizard for new users
@main.command("setup")
def setup_wizard():
    """Interactive setup wizard for new users."""
    show_banner()

    console.print(Panel(
        "[bold cyan]Welcome to DarkCode Server![/]\n\n"
        "This wizard will help you configure your server.\n"
        "You can change these settings later with 'darkcode config'.",
        title="Setup Wizard",
        border_style="cyan",
    ))

    config = ServerConfig.load()
    is_new = not (config.config_dir / ".env").exists()

    # Step 1: Working directory
    console.print("\n[bold cyan]Step 1: Working Directory[/]")
    console.print("[dim]This is where Claude Code will operate.[/]\n")

    working_dir = Prompt.ask(
        "Working directory",
        default=str(config.working_dir),
    )
    config.working_dir = Path(working_dir)

    # Step 2: Port
    console.print("\n[bold cyan]Step 2: Server Port[/]")
    console.print("[dim]Default is 3100. Change if that port is in use.[/]\n")

    port = Prompt.ask("Port", default=str(config.port))
    config.port = int(port)

    # Step 3: Connection mode
    console.print("\n[bold cyan]Step 3: Connection Mode[/]")

    tailscale_ip = config.get_tailscale_ip()
    mode_table = Table(show_header=False, box=None, padding=(0, 2))
    mode_table.add_column("", style="bold cyan", width=4)
    mode_table.add_column("", style="white")

    mode_table.add_row("[1]", "Direct LAN [dim]- Connect over local network[/]")
    if tailscale_ip:
        mode_table.add_row("[2]", f"Tailscale [green](detected: {tailscale_ip})[/] [dim]- Secure mesh VPN[/]")
    else:
        mode_table.add_row("[2]", "Tailscale [dim]- Secure mesh VPN (not detected)[/]")
    mode_table.add_row("[3]", "SSH Tunnel [dim]- Localhost only, most secure[/]")

    console.print(mode_table)

    mode = Prompt.ask("\nSelect mode", default="1", choices=["1", "2", "3"])
    config.local_only = (mode == "3")

    # Step 4: Security
    console.print("\n[bold cyan]Step 4: Security Settings[/]")

    device_lock = Confirm.ask(
        "Lock server to first device that connects?",
        default=config.device_lock,
    )
    config.device_lock = device_lock

    enable_tls = Confirm.ask(
        "Enable TLS encryption (wss://)?",
        default=config.tls_enabled,
    )
    config.tls_enabled = enable_tls

    # Step 5: Save and show summary
    config.save()

    console.print(Panel(
        f"[bold green]Setup Complete![/]\n\n"
        f"[cyan]Working Dir:[/] {config.working_dir}\n"
        f"[cyan]Port:[/] {config.port}\n"
        f"[cyan]Mode:[/] {'SSH Tunnel' if config.local_only else 'Direct/Tailscale'}\n"
        f"[cyan]Device Lock:[/] {'enabled' if config.device_lock else 'disabled'}\n"
        f"[cyan]TLS:[/] {'enabled' if config.tls_enabled else 'disabled'}\n\n"
        f"[cyan]Auth Token:[/] [bold]{config.token}[/]\n\n"
        f"[dim]Save this token! You need it to connect from the app.[/]",
        title="Configuration Saved",
        border_style="green",
    ))

    console.print("\n[bold cyan]Next Steps:[/]")
    console.print("  1. Start the server: [bold]darkcode start[/]")
    console.print("  2. Scan the QR code with the DarkCode app")
    console.print("  3. (Optional) Create guest codes: [bold]darkcode guest create \"Friend\"[/]")

    if is_new:
        start_now = Confirm.ask("\nStart the server now?", default=True)
        if start_now:
            console.print()
            # Import and call start
            from click.testing import CliRunner
            runner = CliRunner()
            runner.invoke(start, ["--no-banner"], standalone_mode=False)


if __name__ == "__main__":
    main()
