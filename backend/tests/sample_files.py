"""Small files built on the fly for upload tests: real PDFs and DOCX, and a few nasty ones."""

import io
import zipfile
from typing import Any

import pymupdf as _pymupdf

# PyMuPDF's type hints are incomplete: treat it as untyped here.
pymupdf: Any = _pymupdf


def pdf(pages: int = 1, text: str = "Contrato de prueba", *, password: str | None = None) -> bytes:
    document = pymupdf.open()
    for number in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"{text} - página {number + 1}")
    options = {}
    if password is not None:
        options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "user_pw": password, "owner_pw": "o"}
    data: bytes = document.tobytes(**options)
    document.close()
    return data


def pdf_with_owner_password_only() -> bytes:
    """Restrictions on printing/copying, but opens without a password: acceptable."""
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Solo lectura")
    data: bytes = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="", owner_pw="owner"
    )
    document.close()
    return data


def docx(text: str = "Hola", pages: int | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            'content-types"><Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            f'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p>'
            "</w:body></w:document>",
        )
        if pages is not None:
            archive.writestr("docProps/app.xml", f"<Properties><Pages>{pages}</Pages></Properties>")
    return buffer.getvalue()


def plain_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("nota.txt", "hola")
    return buffer.getvalue()


def zip_bomb_docx(expanded_bytes: int) -> bytes:
    """A small DOCX that expands to `expanded_bytes` (zeros compress about 1000 to 1)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", b"\0" * expanded_bytes)
    return buffer.getvalue()


def windows_exe() -> bytes:
    """The start of a Windows executable (MZ header): what a renamed virus looks like."""
    header = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 44
    return header + b"\x00" * 200 + b"This program cannot be run in DOS mode.\r\n" + b"\x00" * 300


def broken_pdf() -> bytes:
    return b"%PDF-1.7\n" + b"esto no es un PDF de verdad " * 20
