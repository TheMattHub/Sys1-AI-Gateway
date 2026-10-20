"""Provider-agnostic System-1 decision gateway, exposed to Claude Code as an MCP stdio server."""

import logging

__version__ = "0.1.12"

# Library convention: stay silent unless the server (or an embedding app) configures logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())
