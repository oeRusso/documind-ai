"""Regenerate the sample documents of this folder (they are committed; run only to change them).

uv run python -m tests.fixtures.make_fixtures
"""

from pathlib import Path
from typing import Any

import pymupdf as _pymupdf
from docx import Document as DocxDocument

pymupdf: Any = _pymupdf
HERE = Path(__file__).parent

CONTRACT = [
    (
        "CLÁUSULA PRIMERA - OBJETO",
        "El Proveedor se obliga a prestar el servicio de mantenimiento de los equipos de "
        "climatización de las oficinas del Cliente, ubicadas en Av. Corrientes 1234, CABA.",
    ),
    (
        "CLÁUSULA SEGUNDA - PLAZO",
        "El presente contrato tendrá una duración de doce (12) meses contados desde su firma. "
        "Cualquiera de las partes podrá rescindirlo con un preaviso de treinta (30) días corridos.",
    ),
    (
        "CLÁUSULA TERCERA - PRECIO Y FORMA DE PAGO",
        "El Cliente abonará un precio mensual de pesos cuatrocientos mil ($400.000), dentro de "
        "los diez (10) días de recibida la factura. La mora se producirá de pleno derecho.",
    ),
]


def contract_pdf() -> None:
    document = pymupdf.open()
    for number, (heading, body) in enumerate(CONTRACT, start=1):
        page = document.new_page()
        page.insert_text((72, 40), "ACME S.A. - Contrato de mantenimiento", fontsize=8)
        if number == 1:
            page.insert_text((72, 90), "CONTRATO DE SERVICIOS", fontsize=18)
        page.insert_text((72, 130), heading, fontsize=13)
        box = pymupdf.Rect(72, 145, 520, 400)
        page.insert_textbox(box, body, fontsize=10)
        page.insert_text((280, 800), f"Página {number} de {len(CONTRACT)}", fontsize=8)
    document.save(HERE / "contrato.pdf", garbage=4, deflate=True)


def scanned_pdf() -> None:
    """A page that is only an image of text, like a scanner produces (no text layer)."""
    source = pymupdf.open()
    page = source.new_page(width=420, height=300)
    page.insert_text((30, 60), "ANEXO DE SEGURIDAD", fontsize=20)
    page.insert_text((30, 110), "El personal deberá usar casco", fontsize=16)
    page.insert_text((30, 140), "y calzado de seguridad en planta.", fontsize=16)
    picture = page.get_pixmap(dpi=200)
    scanned = pymupdf.open()
    target = scanned.new_page(width=420, height=300)
    target.insert_image(target.rect, pixmap=picture)
    scanned.save(HERE / "escaneado.pdf", garbage=4, deflate=True)


def policy_docx() -> None:
    document = DocxDocument()
    document.add_heading("Política de viáticos", level=1)
    document.add_paragraph("Esta política aplica a todo el personal que viaje por trabajo.")
    document.add_heading("Montos diarios", level=2)
    document.add_paragraph("Los montos se actualizan cada seis meses.")
    table = document.add_table(rows=3, cols=2)
    for row, (zone, amount) in zip(
        table.rows, [("Zona", "Monto"), ("CABA", "$30.000"), ("Interior", "$25.000")], strict=True
    ):
        row.cells[0].text, row.cells[1].text = zone, amount
    document.add_heading("Rendición", level=2)
    document.add_paragraph("Los comprobantes se presentan dentro de los cinco días hábiles.")
    document.save(str(HERE / "politica.docx"))


def main() -> None:
    contract_pdf()
    scanned_pdf()
    policy_docx()
    print("fixtures written to", HERE)


if __name__ == "__main__":
    main()
