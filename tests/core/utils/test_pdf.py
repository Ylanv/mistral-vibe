from __future__ import annotations

import pytest
from pathlib import Path

from vibe.core.utils.pdf import (
    PDFConversionError,
    convert_pdf_to_markdown,
    convert_pdf_to_markdown_sync,
)


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a sample PDF file for testing."""
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << >> /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000058 00000 n\n0000000106 00000 n\ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n149\n%%EOF"
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(pdf_content)
    return pdf_path


@pytest.fixture
def empty_pdf_path(tmp_path: Path) -> Path:
    """Create an empty PDF file for testing."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"")
    return pdf_path


class TestPDFConversionSync:
    """Tests for synchronous PDF conversion."""

    def test_convert_nonexistent_pdf(self, tmp_path: Path) -> None:
        """Test that converting a nonexistent PDF raises an error."""
        nonexistent = tmp_path / "nonexistent.pdf"
        with pytest.raises(PDFConversionError) as exc_info:
            convert_pdf_to_markdown_sync(nonexistent)
        assert "not found" in exc_info.value.message
        assert exc_info.value.path == nonexistent

    def test_convert_directory(self, tmp_path: Path) -> None:
        """Test that converting a directory raises an error."""
        with pytest.raises(PDFConversionError) as exc_info:
            convert_pdf_to_markdown_sync(tmp_path)
        assert "not a file" in exc_info.value.message

    def test_convert_empty_pdf(self, empty_pdf_path: Path) -> None:
        """Test that converting an empty PDF raises an error."""
        with pytest.raises(PDFConversionError) as exc_info:
            convert_pdf_to_markdown_sync(empty_pdf_path)
        assert "empty" in exc_info.value.message


class TestPDFConversionAsync:
    """Tests for asynchronous PDF conversion."""

    @pytest.mark.asyncio
    async def test_convert_nonexistent_pdf_async(self, tmp_path: Path) -> None:
        """Test that converting a nonexistent PDF raises an error asynchronously."""
        nonexistent = tmp_path / "nonexistent.pdf"
        with pytest.raises(PDFConversionError) as exc_info:
            await convert_pdf_to_markdown(nonexistent)
        assert "not found" in exc_info.value.message


class TestPDFPathPrompt:
    """Tests for PDF detection in path prompt."""

    def test_pdf_extension_detection(self) -> None:
        """Test that .pdf extension is in PDF_EXTENSIONS."""
        from vibe.core.types import PDF_EXTENSIONS
        assert ".pdf" in PDF_EXTENSIONS

    def test_pdf_resource_classification(self, tmp_path: Path) -> None:
        """Test that PDF files are classified as 'pdf' kind."""
        from vibe.core.autocompletion.path_prompt import PathResource, build_path_prompt_payload

        # Create a dummy PDF file
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        payload = build_path_prompt_payload(f"@test.pdf", base_dir=tmp_path)

        # Find the PDF resource
        pdf_resources = [r for r in payload.resources if r.kind == "pdf"]
        assert len(pdf_resources) == 1
        assert pdf_resources[0].path == pdf_path
        assert pdf_resources[0].alias == "test.pdf"
        assert pdf_resources[0].kind == "pdf"

    def test_pdf_with_absolute_path(self, tmp_path: Path) -> None:
        """Test PDF detection with absolute path."""
        from vibe.core.autocompletion.path_prompt import build_path_prompt_payload

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        payload = build_path_prompt_payload(f"@{pdf_path}")
        pdf_resources = [r for r in payload.resources if r.kind == "pdf"]
        assert len(pdf_resources) == 1

    def test_multiple_pdfs(self, tmp_path: Path) -> None:
        """Test detection of multiple PDF files."""
        from vibe.core.autocompletion.path_prompt import build_path_prompt_payload

        pdf1 = tmp_path / "file1.pdf"
        pdf2 = tmp_path / "file2.pdf"
        pdf1.write_bytes(b"%PDF-1.4")
        pdf2.write_bytes(b"%PDF-1.4")

        payload = build_path_prompt_payload(f"@file1.pdf and @file2.pdf", base_dir=tmp_path)
        pdf_resources = [r for r in payload.resources if r.kind == "pdf"]
        assert len(pdf_resources) == 2

    def test_pdf_mixed_with_other_files(self, tmp_path: Path) -> None:
        """Test PDF detection mixed with other file types."""
        from vibe.core.autocompletion.path_prompt import build_path_prompt_payload

        pdf_path = tmp_path / "doc.pdf"
        txt_path = tmp_path / "notes.txt"
        py_path = tmp_path / "script.py"

        pdf_path.write_bytes(b"%PDF-1.4")
        txt_path.write_bytes(b"text content")
        py_path.write_bytes(b"print('hello')")

        payload = build_path_prompt_payload(
            f"@doc.pdf @notes.txt @script.py", base_dir=tmp_path
        )

        pdf_resources = [r for r in payload.resources if r.kind == "pdf"]
        file_resources = [r for r in payload.resources if r.kind == "file"]

        assert len(pdf_resources) == 1
        assert len(file_resources) == 2
        assert pdf_resources[0].path == pdf_path


