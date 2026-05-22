"""
Creates a formatted PDF permit application form from a JSON file.

Usage:
    python samples/tools/create_permit_pdf.py <input.json> [output.pdf]

Example:
    python samples/tools/create_permit_pdf.py samples/use-cases/one/files/permit_app_001.json
"""

import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)


# ── Styles ────────────────────────────────────────────────────────────────────

_BASE = getSampleStyleSheet()

TITLE_STYLE = ParagraphStyle(
    "PermitTitle",
    parent=_BASE["Title"],
    fontSize=18,
    textColor=colors.HexColor("#1a3a5c"),
    spaceAfter=4,
)

SECTION_STYLE = ParagraphStyle(
    "SectionHeader",
    parent=_BASE["Heading2"],
    fontSize=11,
    textColor=colors.white,
    backColor=colors.HexColor("#1a3a5c"),
    spaceBefore=12,
    spaceAfter=4,
    leftIndent=6,
    rightIndent=6,
)

LABEL_STYLE = ParagraphStyle(
    "FieldLabel",
    parent=_BASE["Normal"],
    fontSize=8,
    textColor=colors.HexColor("#555555"),
    spaceAfter=1,
)

VALUE_STYLE = ParagraphStyle(
    "FieldValue",
    parent=_BASE["Normal"],
    fontSize=10,
    textColor=colors.black,
    spaceAfter=6,
)

FOOTER_STYLE = ParagraphStyle(
    "Footer",
    parent=_BASE["Normal"],
    fontSize=8,
    textColor=colors.grey,
    alignment=1,  # center
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _field_row(label: str, value: str) -> list:
    """Returns a two-cell table row: label above value."""
    return [
        Paragraph(label.upper(), LABEL_STYLE),
        Paragraph(str(value) if value is not None else "—", VALUE_STYLE),
    ]


def _section(title: str) -> Paragraph:
    return Paragraph(f"  {title}", SECTION_STYLE)


def _two_col_table(rows: list[tuple[str, str]], col_widths=None) -> Table:
    """Builds a simple two-column label/value table."""
    if col_widths is None:
        col_widths = [2.2 * inch, 4.3 * inch]
    data = [[Paragraph(lbl.upper(), LABEL_STYLE), Paragraph(str(val), VALUE_STYLE)]
            for lbl, val in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
    ]))
    return t


def _four_col_table(rows: list[tuple], col_widths=None) -> Table:
    """Builds a four-column label/value/label/value table."""
    if col_widths is None:
        col_widths = [1.5 * inch, 2.0 * inch, 1.5 * inch, 1.5 * inch]
    data = [
        [
            Paragraph(rows[i][0].upper(), LABEL_STYLE),
            Paragraph(str(rows[i][1]), VALUE_STYLE),
            Paragraph(rows[i][2].upper(), LABEL_STYLE) if i < len(
                rows) and len(rows[i]) > 2 else "",
            Paragraph(str(rows[i][3]), VALUE_STYLE) if i < len(
                rows) and len(rows[i]) > 3 else "",
        ]
        for i in range(len(rows))
    ]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
    ]))
    return t


# ── Builder ───────────────────────────────────────────────────────────────────

def build_permit_pdf(data: dict, output_path: str) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    story = []

    # ── Header ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Building Permit Application", TITLE_STYLE))
    story.append(HRFlowable(width="100%", thickness=2,
                 color=colors.HexColor("#1a3a5c")))
    story.append(Spacer(1, 6))

    header_rows = [
        ("Application ID", data.get("application_id", "—"),
         "Submission Date", data.get("submission_date", "—")),
        ("Permit Type", data.get("permit_type", "—"),
         "Parcel Number", data.get("parcel_number") or ""),
    ]
    story.append(_four_col_table(header_rows, col_widths=[
        1.4 * inch, 2.1 * inch, 1.4 * inch, 1.6 * inch
    ]))

    # ── Property Address ───────────────────────────────────────────────────
    story.append(_section("Property Address"))
    addr = data.get("property_address", {})
    full_address = ", ".join(filter(None, [
        addr.get("street"),
        addr.get("city"),
        addr.get("state"),
        addr.get("zip"),
    ]))
    story.append(_two_col_table([
        ("Street", addr.get("street", "—")),
        ("City / State / ZIP",
         f"{addr.get('city', '—')}, {addr.get('state', '—')}  {addr.get('zip', '—')}"),
    ]))

    # ── Project Description ────────────────────────────────────────────────
    story.append(_section("Project Description"))
    story.append(_two_col_table([
        ("Description", data.get("project_description", "—")),
        ("Estimated Cost", f"${data.get('estimated_cost') or 0:,.2f}"),
    ]))

    # ── Applicant ──────────────────────────────────────────────────────────
    story.append(_section("Applicant Information"))
    applicant = data.get("applicant", {})
    story.append(_two_col_table([
        ("Name", applicant.get("name", "—")),
        ("Phone", applicant.get("phone", "—")),
        ("Email", applicant.get("email", "—")),
        ("Signature", applicant.get("signature") or ""),
        ("Signature Date", applicant.get("signature_date") or ""),
    ]))

    # ── Contractor ─────────────────────────────────────────────────────────
    story.append(_section("Contractor Information"))
    contractor = data.get("contractor", {})
    story.append(_two_col_table([
        ("Name", contractor.get("name", "—")),
        ("License Number", contractor.get("license_number", "—")),
        ("Phone", contractor.get("phone", "—")),
    ]))

    # ── Footer ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Generated from {Path(output_path).name}  •  Application {data.get('application_id', '')}",
        FOOTER_STYLE,
    ))

    doc.build(story)
    print(f"PDF created: {output_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    json_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else Path(
        json_path).with_suffix(".pdf")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    build_permit_pdf(data, str(output_path))


if __name__ == "__main__":
    main()
