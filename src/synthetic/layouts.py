"""ReportLab layouts for generating 4 distinct synthetic lab report styles.

Layout A: Simple clean table (Test | Result | Unit | Reference Range)
Layout B: Sectioned panels (CBC, Lipid, Liver, etc.) with printed H/L flag column
Layout C: Compact two-column format
Layout D: Mixed styles with multi-tier ranges and one-sided ranges
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Bundled TTF font registration
FONT_DIR = Path(__file__).resolve().parent / "fonts"
VERA_TTF = FONT_DIR / "Vera.ttf"
VERA_BD_TTF = FONT_DIR / "VeraBd.ttf"

_FONTS_REGISTERED = False


def ensure_fonts_registered() -> None:
    """Register bundled Vera fonts for ReportLab."""
    global _FONTS_REGISTERED
    if not _FONTS_REGISTERED:
        pdfmetrics.registerFont(TTFont("Vera", str(VERA_TTF)))
        pdfmetrics.registerFont(TTFont("Vera-Bold", str(VERA_BD_TTF)))
        _FONTS_REGISTERED = True


def make_header_elements(header: dict[str, Any]) -> List[Any]:
    """Generate the fake lab and patient header elements.

    Enforces: Clinical_Context is NEVER printed.
    """
    ensure_fonts_registered()
    elements: List[Any] = []

    title_style = ParagraphStyle(
        "LabTitle",
        fontName="Vera-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1A365D"),
        alignment=1,  # Center
    )
    sub_style = ParagraphStyle(
        "LabSub",
        fontName="Vera",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4A5568"),
        alignment=1,
    )
    meta_label = ParagraphStyle(
        "MetaLabel",
        fontName="Vera-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#2D3748"),
    )
    meta_val = ParagraphStyle(
        "MetaVal",
        fontName="Vera",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1A202C"),
    )

    # 1. Lab Header
    elements.append(Paragraph(header["lab_name"].upper(), title_style))
    elements.append(Paragraph(f"{header['lab_address']} | Phone: {header['lab_phone']}", sub_style))
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2B6CB0"), spaceAfter=8))

    # 2. Patient Demographics Grid (2 rows x 4 cols)
    # Row 1: Patient Name, Patient ID, Age / Sex, Ref Doctor
    # Row 2: Contact Phone, Sample Collected, Report Generated, Status: Final
    p_name = f"<b>Patient:</b> {header['patient_name']}"
    p_id = f"<b>ID:</b> {header['patient_id']}"
    p_age_sex = f"<b>Age/Sex:</b> {header['age']} Y / {header['gender']}"
    p_doc = f"<b>Ref By:</b> {header['doctor']}"

    p_phone = f"<b>Contact:</b> {header['phone']}"
    p_coll = f"<b>Collected:</b> {header['collection_date']}"
    p_rep = f"<b>Reported:</b> {header['report_date']}"
    p_status = "<b>Status:</b> Final Verified"

    header_data = [
        [
            Paragraph(p_name, meta_val),
            Paragraph(p_id, meta_val),
            Paragraph(p_age_sex, meta_val),
            Paragraph(p_doc, meta_val),
        ],
        [
            Paragraph(p_phone, meta_val),
            Paragraph(p_coll, meta_val),
            Paragraph(p_rep, meta_val),
            Paragraph(p_status, meta_val),
        ],
    ]

    header_table = Table(header_data, colWidths=[2.2 * inch, 1.2 * inch, 1.4 * inch, 2.4 * inch])
    header_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 10))
    return elements


def render_layout_a(pdf_path: Path, header: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Render Layout A: Simple Table (Test Name | Result | Unit | Reference Range)."""
    ensure_fonts_registered()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    elements = make_header_elements(header)

    th_style = ParagraphStyle(
        "TH",
        fontName="Vera-Bold",
        fontSize=9,
        leading=11,
        textColor=colors.white,
    )
    td_style = ParagraphStyle(
        "TD",
        fontName="Vera",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#2D3748"),
    )
    td_bold = ParagraphStyle(
        "TDBold",
        fontName="Vera-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1A202C"),
    )

    table_data = [
        [
            Paragraph("TEST / PARAMETER", th_style),
            Paragraph("OBSERVED VALUE", th_style),
            Paragraph("UNIT", th_style),
            Paragraph("REFERENCE RANGE", th_style),
        ]
    ]

    for r in rows:
        table_data.append(
            [
                Paragraph(r["printed_name"], td_bold),
                Paragraph(r["printed_value_text"], td_style),
                Paragraph(r["unit"], td_style),
                Paragraph(r["printed_range_text"], td_style),
            ]
        )

    col_widths = [2.7 * inch, 1.4 * inch, 1.4 * inch, 2.0 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ]
        )
    )
    elements.append(t)
    doc.build(elements)


def render_layout_b(pdf_path: Path, header: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Render Layout B: Sectioned panels with printed H/L flag markers."""
    ensure_fonts_registered()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    elements = make_header_elements(header)

    th_style = ParagraphStyle("TH_B", fontName="Vera-Bold", fontSize=8.5, leading=10, textColor=colors.HexColor("#2C5282"))
    sec_style = ParagraphStyle("SEC_B", fontName="Vera-Bold", fontSize=9.5, leading=12, textColor=colors.HexColor("#2B6CB0"))
    td_style = ParagraphStyle("TD_B", fontName="Vera", fontSize=8, leading=10, textColor=colors.HexColor("#2D3748"))
    td_bold = ParagraphStyle("TDB_B", fontName="Vera-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#1A202C"))
    td_flag = ParagraphStyle("TDF_B", fontName="Vera-Bold", fontSize=8.5, leading=10, textColor=colors.HexColor("#C53030"))

    # Group rows by section
    sections: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        sec = r.get("section") or "General Clinical Chemistry"
        sections.setdefault(sec, []).append(r)

    table_data = [
        [
            Paragraph("INVESTIGATION", th_style),
            Paragraph("RESULT", th_style),
            Paragraph("FLAG", th_style),
            Paragraph("UNIT", th_style),
            Paragraph("BIOLOGICAL REFERENCE INTERVAL", th_style),
        ]
    ]

    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EBF8FF")),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#3182CE")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    curr_row_idx = 1
    for sec_name, sec_rows in sections.items():
        # Add section subheader row spanning all 5 columns
        table_data.append([
            Paragraph(f"<b>{sec_name.upper()}</b>", sec_style), "", "", "", ""
        ])
        row_styles.append(("SPAN", (0, curr_row_idx), (-1, curr_row_idx)))
        row_styles.append(("BACKGROUND", (0, curr_row_idx), (-1, curr_row_idx), colors.HexColor("#EDF2F7")))
        row_styles.append(("TOPPADDING", (0, curr_row_idx), (-1, curr_row_idx), 4))
        row_styles.append(("BOTTOMPADDING", (0, curr_row_idx), (-1, curr_row_idx), 4))
        curr_row_idx += 1

        for r in sec_rows:
            flag_marker = r.get("printed_flag_marker") or ""
            table_data.append([
                Paragraph(r["printed_name"], td_bold),
                Paragraph(r["printed_value_text"], td_style),
                Paragraph(f"<b>{flag_marker}</b>" if flag_marker else "", td_flag),
                Paragraph(r["unit"], td_style),
                Paragraph(r["printed_range_text"], td_style),
            ])
            curr_row_idx += 1

    col_widths = [2.5 * inch, 1.2 * inch, 0.6 * inch, 1.2 * inch, 2.0 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(row_styles))
    elements.append(t)
    doc.build(elements)


def render_layout_c(pdf_path: Path, header: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Render Layout C: Compact two-column layout."""
    ensure_fonts_registered()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    elements = make_header_elements(header)

    th_style = ParagraphStyle("TH_C", fontName="Vera-Bold", fontSize=7.5, leading=9, textColor=colors.white)
    td_name = ParagraphStyle("TDN_C", fontName="Vera-Bold", fontSize=7.5, leading=9, textColor=colors.HexColor("#1A202C"))
    td_val = ParagraphStyle("TDV_C", fontName="Vera", fontSize=7.5, leading=9, textColor=colors.HexColor("#2D3748"))
    td_rng = ParagraphStyle("TDR_C", fontName="Vera", fontSize=7.5, leading=9, textColor=colors.HexColor("#4A5568"))

    # Split rows into two columns
    half = (len(rows) + 1) // 2
    left_rows = rows[:half]
    right_rows = rows[half:]

    table_data = [
        [
            Paragraph("TEST", th_style), Paragraph("VALUE", th_style), Paragraph("REF RANGE", th_style),
            "",
            Paragraph("TEST", th_style), Paragraph("VALUE", th_style), Paragraph("REF RANGE", th_style),
        ]
    ]

    for i in range(max(len(left_rows), len(right_rows))):
        lr = left_rows[i] if i < len(left_rows) else None
        rr = right_rows[i] if i < len(right_rows) else None

        l_name = Paragraph(lr["printed_name"], td_name) if lr else ""
        l_val = Paragraph(f"{lr['printed_value_text']} {lr['unit']}", td_val) if lr else ""
        l_rng = Paragraph(lr["printed_range_text"], td_rng) if lr else ""

        r_name = Paragraph(rr["printed_name"], td_name) if rr else ""
        r_val = Paragraph(f"{rr['printed_value_text']} {rr['unit']}", td_val) if rr else ""
        r_rng = Paragraph(rr["printed_range_text"], td_rng) if rr else ""

        table_data.append([l_name, l_val, l_rng, "", r_name, r_val, r_rng])

    col_widths = [1.5 * inch, 1.1 * inch, 1.1 * inch, 0.1 * inch, 1.5 * inch, 1.1 * inch, 1.1 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (2, 0), colors.HexColor("#4A5568")),
                ("BACKGROUND", (4, 0), (6, 0), colors.HexColor("#4A5568")),
                ("GRID", (0, 0), (2, -1), 0.5, colors.HexColor("#CBD5E0")),
                ("GRID", (4, 0), (6, -1), 0.5, colors.HexColor("#CBD5E0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (2, -1), [colors.white, colors.HexColor("#F7FAFC")]),
                ("ROWBACKGROUNDS", (4, 1), (6, -1), [colors.white, colors.HexColor("#F7FAFC")]),
            ]
        )
    )
    elements.append(t)
    doc.build(elements)


def render_layout_d(pdf_path: Path, header: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Render Layout D: Mixed styles with multi-tier ranges, one-sided ranges, and alternate units."""
    ensure_fonts_registered()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    elements = make_header_elements(header)

    th_style = ParagraphStyle("TH_D", fontName="Vera-Bold", fontSize=8.5, leading=10, textColor=colors.HexColor("#742A2A"))
    td_bold = ParagraphStyle("TDB_D", fontName="Vera-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#1A202C"))
    td_val = ParagraphStyle("TDV_D", fontName="Vera", fontSize=8, leading=10, textColor=colors.HexColor("#2D3748"))
    td_unit = ParagraphStyle("TDU_D", fontName="Vera", fontSize=8, leading=10, textColor=colors.HexColor("#4A5568"))
    td_rng = ParagraphStyle("TDR_D", fontName="Vera", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#2D3748"))

    table_data = [
        [
            Paragraph("TEST SPECIFICATION", th_style),
            Paragraph("PATIENT VALUE", th_style),
            Paragraph("UNIT", th_style),
            Paragraph("INTERPRETIVE REFERENCE CRITERIA", th_style),
        ]
    ]

    for r in rows:
        table_data.append([
            Paragraph(r["printed_name"], td_bold),
            Paragraph(r["printed_value_text"], td_val),
            Paragraph(r["unit"], td_unit),
            Paragraph(r["printed_range_text"], td_rng),
        ])

    col_widths = [2.4 * inch, 1.3 * inch, 1.1 * inch, 2.7 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FFF5F5")),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#E53E3E")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#FED7D7")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFFDFD")]),
            ]
        )
    )
    elements.append(t)
    doc.build(elements)
