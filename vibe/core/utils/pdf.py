from __future__ import annotations
from markitdown import MarkItDown

import asyncio
from pathlib import Path

from vibe.core.logger import logger

try:
    import markitdown
    MARKITDOWN_AVAILABLE = True
    md = MarkItDown(enable_plugins=False) # Set to True to enable plugins
except ImportError:
    MARKITDOWN_AVAILABLE = False
    markitdown = None  # type: ignore


class PDFConversionError(Exception):
    """Raised when PDF conversion fails."""

    def __init__(self, message: str, path: Path | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.path = path


def _check_markitdown_available() -> None:
    """Check if markitdown is available."""
    if not MARKITDOWN_AVAILABLE:
        raise PDFConversionError(
            "PDF support requires the 'markitdown' package. "
            "Install it with: uv add markitdown"
        )


def convert_pdf_to_markdown_sync(path: Path) -> str:
    """
    Convert a PDF file to Markdown synchronously.

    Args:
        path: Path to the PDF file

    Returns:
        The Markdown content as a string

    Raises:
        PDFConversionError: If conversion fails for any reason
    """
    _check_markitdown_available()

    if not path.exists():
        raise PDFConversionError(f"PDF file not found: {path}", path=path)

    if not path.is_file():
        raise PDFConversionError(f"Path is not a file: {path}", path=path)

    try:
        # Read the PDF file as bytes
        pdf_bytes = path.read_bytes()
    except OSError as e:
        raise PDFConversionError(f"Failed to read PDF file {path}: {e}", path=path) from e

    if not pdf_bytes:
        raise PDFConversionError(f"PDF file is empty: {path}", path=path)

    try:
        # Convert PDF to Markdown using markitdown
        # API: MarkItDown.convert(path) returns ConversionResult with .text_content
        result = md.convert(str(path))
        markdown_content = result.text_content

        if not markdown_content:
            raise PDFConversionError(f"PDF conversion returned empty content: {path}", path=path)

        return markdown_content

    except Exception as e:
        # Catch various PDF-related errors
        error_msg = str(e).lower()
        if "encrypted" in error_msg or "password" in error_msg:
            raise PDFConversionError(f"PDF is encrypted and cannot be read: {path}", path=path) from e
        elif "corrupt" in error_msg or "invalid" in error_msg:
            raise PDFConversionError(f"PDF is corrupted or invalid: {path}", path=path) from e
        else:
            raise PDFConversionError(f"Failed to convert PDF {path}: {e}", path=path) from e


async def convert_pdf_to_markdown(path: Path) -> str:
    """
    Convert a PDF file to Markdown asynchronously.

    This runs the synchronous conversion in a thread to avoid blocking the event loop.

    Args:
        path: Path to the PDF file

    Returns:
        The Markdown content as a string

    Raises:
        PDFConversionError: If conversion fails for any reason
    """
    return await asyncio.to_thread(convert_pdf_to_markdown_sync, path)


