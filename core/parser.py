"""Extract plain text from uploaded resume / job description files."""

from __future__ import annotations

import io
import re

from docx import Document
from pypdf import PdfReader

SUPPORTED_TYPES = ["pdf", "docx", "txt", "md"]


class ParseError(Exception):
    """Raised when a file can't be turned into usable text."""


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(filename: str, data: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext == "pdf":
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext == "docx":
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(parts)
        elif ext in ("txt", "md"):
            text = data.decode("utf-8", errors="ignore")
        else:
            raise ParseError(f"Unsupported file type: .{ext}")
    except ParseError:
        raise
    except Exception as exc:  # corrupt / encrypted files
        raise ParseError(f"Could not read {filename}: {exc}") from exc

    text = _clean(text)
    if len(text) < 50:
        raise ParseError(
            f"Very little text was found in {filename}. If it is a scanned image PDF, "
            "export it as a text-based PDF or DOCX and try again."
        )
    return text
