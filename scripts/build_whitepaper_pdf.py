#!/usr/bin/env python3
"""
LockTrace (BCT) Official Whitepaper PDF Generator
=================================================
Converts docs/WHITEPAPER.md into a high-fidelity, publication-grade PDF whitepaper
matching the latest protocol version (v2.9.0).
"""

import os
import sys
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WP_MD_PATH = os.path.join(ROOT_DIR, "docs", "WHITEPAPER.md")
PDF_OUTPUT_PATH = os.path.join(ROOT_DIR, "docs", "LockTrace_Whitepaper.pdf")

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and print total page count."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Do not print header on page 1 (cover)
        if self._pageNumber > 1:
            # Running Header
            self.drawString(54, 800, "LockTrace (BCT) Technical Whitepaper — Protocol Specification v2.9.0")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(54, 792, 541, 792)

        # Running Footer (all pages)
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 541, 45)
        self.drawString(54, 32, "https://www.locktrace.space | Base Mainnet: 0xA3C743113a41cFd0146917065d4578337Bb77254")
        self.drawRightString(541, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()

def clean_markdown_inline(text: str) -> str:
    """Cleans LaTeX and markdown markup for ReportLab Paragraph rendering."""
    # Escape HTML special chars first
    t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Protect inline code spans so their content (e.g. *, _, $) is not mangled
    code_blocks = []
    def code_replacer(m):
        code_blocks.append(m.group(1))
        return f"___CODE_BLOCK_{len(code_blocks) - 1}___"

    t = re.sub(r'`(.*?)`', code_replacer, t)

    # Restore basic formatting
    t = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'\*(.*?)\*', r'<i>\1</i>', t)

    # LaTeX math replacements
    t = re.sub(r'\\text\{([^}]+)\}', r'\1', t)
    t = re.sub(r'\\ne', r'&ne;', t)
    t = re.sub(r'\\times', r'&times;', t)
    t = re.sub(r'\\ge', r'&ge;', t)
    t = re.sub(r'\\le', r'&le;', t)
    t = re.sub(r'\\approx', r'&asymp;', t)
    t = re.sub(r'\$O\((.*?)\)\$', r'<b>O(\1)</b>', t)
    t = re.sub(r'\$(.*?)\$', r'<i>\1</i>', t)

    # Restore styled code spans
    for idx, code_content in enumerate(code_blocks):
        t = t.replace(
            f"___CODE_BLOCK_{idx}___",
            f'<font name="Courier" size="8" color="#0F766E"><b>{code_content}</b></font>'
        )

    return t

def generate_pdf():
    print(f"[*] Reading source whitepaper from: {WP_MD_PATH}")
    with open(WP_MD_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()

    doc = SimpleDocTemplate(
        PDF_OUTPUT_PATH,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom typography palette
    c_primary = colors.HexColor("#0F172A")
    c_secondary = colors.HexColor("#0D9488")
    c_accent = colors.HexColor("#2563EB")
    c_text = colors.HexColor("#1E293B")
    c_muted = colors.HexColor("#64748B")
    c_code_bg = colors.HexColor("#F8FAFC")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=14,
        textColor=c_secondary,
        spaceAfter=14
    )

    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=11,
        textColor=c_muted
    )

    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=c_primary,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=13,
        textColor=c_accent,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=c_text,
        alignment=4, # Justified
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=c_text,
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=3
    )

    code_style = ParagraphStyle(
        'DocCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0F766E"),
        backColor=c_code_bg,
        borderPadding=4,
        spaceBefore=4,
        spaceAfter=6
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=c_text
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("LockTrace (BCT) Technical Whitepaper", title_style))
    story.append(Paragraph(
        "A High-Throughput Hybrid Proof-of-Work, 3-Phase Atomic CAS Sequencer & Quorum-Attested Layer-1 Blockchain "
        "for Censorship-Resistant SocialFi, Decentralized Naming (.bct), and Self-Sovereign Cross-Chain DeFi",
        subtitle_style
    ))

    meta_box = [
        [
            Paragraph("<b>Protocol Release:</b> v2.9.0 (Production Mainnet)", meta_style),
            Paragraph("<b>Release Authority:</b> BCT885bc383a03ebed0aa11cedfbfac0d52be3d4080", meta_style)
        ],
        [
            Paragraph("<b>Official Mainnet:</b> https://www.locktrace.space", meta_style),
            Paragraph("<b>Bridge Proof-of-Reserve Vault:</b> BCT_BRIDGE_VAULT_000000000000000000000000000000000", meta_style)
        ],
        [
            Paragraph("<b>Base Mainnet wBCT ERC-20:</b> 0xA3C743113a41cFd0146917065d4578337Bb77254", meta_style),
            Paragraph("<b>Validator Staking Vault:</b> BCT_STAKE_VAULT_00000000000000000000000000000000", meta_style)
        ]
    ]
    t_meta = Table(meta_box, colWidths=[240, 247])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0D9488"), spaceAfter=10))

    # Process Markdown content line by line
    lines = md_text.split("\n")
    in_code_block = False
    code_buffer = []
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()

        # Skip main header lines already rendered in cover
        if stripped.startswith("# LockTrace") or stripped.startswith("*Version 2.8") or stripped.startswith("*Genesis Release Authority") or stripped.startswith("*Treasury Vault") or stripped.startswith("*Bridge Proof") or stripped.startswith("*Validator Staking") or stripped.startswith("*Provable Burn") or stripped.startswith("*Base Mainnet wBCT"):
            continue

        # Code block toggle
        if stripped.startswith("```"):
            if in_code_block:
                code_text = "\n".join(code_buffer)
                story.append(Paragraph(code_text.replace("\n", "<br/>").replace(" ", "&nbsp;"), code_style))
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_buffer.append(stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue

        # Table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Ignore separator line
            if all(set(c).issubset({"-", ":", " "}) for c in cells):
                continue
            table_rows.append(cells)
            in_table = True
            continue
        elif in_table:
            # End of table, render it
            if table_rows:
                num_cols = len(table_rows[0])
                col_w = 487 / num_cols
                rendered_table = []
                for idx, row in enumerate(table_rows):
                    row_cells = []
                    is_head = (idx == 0)
                    for cell in row:
                        style = table_header_style if is_head else table_cell_style
                        row_cells.append(Paragraph(clean_markdown_inline(cell), style))
                    rendered_table.append(row_cells)
                
                t_obj = Table(rendered_table, colWidths=[col_w] * num_cols)
                t_obj.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F172A")),
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
                    ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                    ('LEFTPADDING', (0,0), (-1,-1), 5),
                    ('RIGHTPADDING', (0,0), (-1,-1), 5),
                ]))
                story.append(Spacer(1, 4))
                story.append(t_obj)
                story.append(Spacer(1, 6))
            table_rows = []
            in_table = False

        if not stripped:
            continue

        # Markdown Headings
        if stripped.startswith("## "):
            story.append(Spacer(1, 6))
            story.append(Paragraph(clean_markdown_inline(stripped[3:]), h1_style))
            continue
        elif stripped.startswith("### "):
            story.append(Paragraph(clean_markdown_inline(stripped[4:]), h2_style))
            continue
        elif stripped.startswith("#### "):
            story.append(Paragraph(clean_markdown_inline(stripped[5:]), h2_style))
            continue

        # Markdown Dividers
        if stripped in ("---", "***"):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=8))
            continue

        # Bullet list items
        if stripped.startswith(("- ", "* ", "+ ")) or re.match(r'^\d+\.\s', stripped):
            clean_item = re.sub(r'^([-*+]|\d+\.)\s+', '', stripped)
            bullet_sym = "&bull; " if stripped.startswith(("- ", "* ", "+ ")) else ""
            story.append(Paragraph(f"{bullet_sym}{clean_markdown_inline(clean_item)}", bullet_style))
            continue

        # Standard Paragraph
        story.append(Paragraph(clean_markdown_inline(stripped), body_style))

    # Build document with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] Built PDF: {PDF_OUTPUT_PATH} ({os.path.getsize(PDF_OUTPUT_PATH):,} bytes)")

    # Distribute to all replica locations
    targets = [
        os.path.join(ROOT_DIR, "LockTrace_Whitepaper.pdf"),
        os.path.join(ROOT_DIR, "frontend", "LockTrace_Whitepaper.pdf"),
        os.path.join(ROOT_DIR, "frontend", "docs", "LockTrace_Whitepaper.pdf"),
    ]
    with open(PDF_OUTPUT_PATH, "rb") as f:
        pdf_bytes = f.read()

    for target in targets:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(pdf_bytes)
        print(f"  -> Synchronized copy to: {target}")

if __name__ == "__main__":
    generate_pdf()

