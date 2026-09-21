"""Local MCP server package for the GOST document checker."""

from .server import app, mcp, parse_document_file

__all__ = ["app", "mcp", "parse_document_file"]
