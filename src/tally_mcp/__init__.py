"""Tally MCP — connect Claude to TallyPrime accounting data.

A custom Model Context Protocol server that talks to TallyPrime's built-in
XML-over-HTTP gateway (default http://localhost:9000) and exposes Tally
reports and master data to Claude as MCP tools.
"""

__version__ = "0.1.0"
