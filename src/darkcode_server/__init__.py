"""DarkCode Server - Remote Claude Code from your phone."""

__version__ = "0.1.8"
__author__ = "0xdeadbeef"

from darkcode_server.server import DarkCodeServer
from darkcode_server.config import ServerConfig

__all__ = ["DarkCodeServer", "ServerConfig", "__version__"]
