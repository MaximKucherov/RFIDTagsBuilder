"""
RFIDTagBuilder v3 — Export Engine
===================================
Excel (.xlsx) and CSV (.csv) writers.
Both formats are ready for direct import into NiceLabel / Loftware,
Zebra ZebraDesigner, SATO CODETHINQ, or any standards-compliant
label printing system.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from models import GROUP_PALETTE_LIGHT, TagGroup

log = logging.getLogger(__name__)

# ── Shared style primitives ──────────────────────────────────────────────────────

_THIN       = Side(border_style="thin", color="AAAAAA")
_BORDER     = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER     = Alignment(horizontal="center", vertical="center")
_LEFT       = Alignment(horizontal="left",   vertical="center")
_ARIAL_9    = Font(name="Arial",      size=9)
_COURIER_8  = Font(name="Courier New", size=8)
_ARIAL_BOLD = Font(name="Arial",      size=10, bold=True)
_BLUE_BOLD  = Font(name="Arial",      size=11, bold=True, color="1565C0")


def _group_fill(g_idx: int) -> PatternFill:
    color = GROUP_PALETTE_LIGHT[g_idx % len(GROUP_PALETTE_LIGHT)].lstrip("#")
    return PatternFill("solid", fgColor=color)


# ── Excel export ─────────────────────────────────────────────────────────────────

def export_excel(groups: list[TagGroup], path: str | Path) -> int:
    """
    Write all groups to an Excel workbook at *path*.

    Sheet 1 — "RFID Tags":  TYP | TXPHEX | NAZOV
    Sheet 2 — "Summary":    one row per group + SPOLU (total) formula

    Returns the total number of tags written.
    """
    path = Path(path)
    wb   = openpyxl.Workbook()

    total = _write_tags_sheet(wb, groups)
    _write_summary_sheet(wb, groups)

    wb.save(path)
    log.info("Excel exported: %s  (%d tags)", path, total)
    return total


def _write_tags_sheet(wb: openpyxl.Workbook, groups: list[TagGroup]) -> int:
    ws       = wb.active
    ws.title = "RFID Tags"

    # Header row
    HDR = [
        ("TYP",    "FFFF00", 30),
        ("TXPHEX", "92D050", 56),
        ("NAZOV",  "BDD7EE", 26),
    ]
    for col_idx, (name, color, width) in enumerate(HDR, start=1):
        cell            = ws.cell(row=1, column=col_idx, value=name)
        cell.font       = _ARIAL_BOLD
        cell.fill       = PatternFill("solid", fgColor=color)
        cell.alignment  = _CENTER
        cell.border     = _BORDER
        ws.column_dimensions[chr(64 + col_idx)].width = width

    ws.row_dimensions[1].height = 18
    ws.freeze_panes = "A2"

    # Data rows — written in batches per group for performance
    row = 2
    for g_idx, g in enumerate(groups):
        fill = _group_fill(g_idx)
        batch: list[tuple] = []

        for tag in g.iter_tags():
            batch.append((tag["TYP"], tag["TXPHEX"], tag["NAZOV"]))

        for typ, txphex, nazov in batch:
            ws.cell(row=row, column=1, value=typ).font    = _ARIAL_9
            ws.cell(row=row, column=2, value=txphex).font = _COURIER_8
            ws.cell(row=row, column=3, value=nazov).font  = _ARIAL_9
            for col_idx in range(1, 4):
                c           = ws.cell(row=row, column=col_idx)
                c.border    = _BORDER
                c.fill      = fill
                c.alignment = _LEFT
            row += 1

    return row - 2   # total tags written


def _write_summary_sheet(wb: openpyxl.Workbook, groups: list[TagGroup]) -> None:
    ws2       = wb.create_sheet("Summary")
    hdr_font  = Font(name="Arial", bold=True, size=10, color="FFFFFF")
    hdr_fill  = PatternFill("solid", fgColor="1565C0")

    S_COLS = [
        ("Group / Prefix", 22),
        ("Description",    26),
        ("EPC Memory",     14),
        ("Counter Range",  22),
        ("A/B",             8),
        ("Tags",           10),
    ]
    for col_idx, (name, width) in enumerate(S_COLS, start=1):
        cell           = ws2.cell(row=1, column=col_idx, value=name)
        cell.font      = hdr_font
        cell.fill      = hdr_fill
        cell.alignment = _CENTER
        cell.border    = _BORDER
        ws2.column_dimensions[chr(64 + col_idx)].width = width

    ws2.row_dimensions[1].height = 20
    ws2.freeze_panes = "A2"

    for row_i, g in enumerate(groups, start=2):
        pad = g.counter_padding
        rng = (
            f"{str(g.counter_start).zfill(pad)}"
            f" – "
            f"{str(g.counter_end).zfill(pad)}"
        )
        epc_label = f"{g.epc_bits} bit ({g.epc_ascii_chars} chars)"
        row_data  = [
            g.prefix, g.nazov, epc_label, rng,
            "A/B" if g.ab_pair else "–", g.count,
        ]
        fill = _group_fill(row_i - 2)
        for col_idx, val in enumerate(row_data, start=1):
            cell           = ws2.cell(row=row_i, column=col_idx, value=val)
            cell.font      = _ARIAL_9
            cell.border    = _BORDER
            cell.fill      = fill
            cell.alignment = _LEFT if col_idx <= 2 else _CENTER

    # SPOLU (total) row
    total_row           = len(groups) + 2
    lbl                 = ws2.cell(row=total_row, column=5, value="SPOLU")
    lbl.font            = _ARIAL_BOLD
    lbl.alignment       = Alignment(horizontal="right")
    lbl.border          = _BORDER

    tot                 = ws2.cell(row=total_row, column=6,
                                   value=f"=SUM(F2:F{total_row - 1})")
    tot.font            = _BLUE_BOLD
    tot.alignment       = _CENTER
    tot.border          = _BORDER
    tot.fill            = PatternFill("solid", fgColor="FFFF00")


# ── CSV export ───────────────────────────────────────────────────────────────────

def export_csv(groups: list[TagGroup], path: str | Path) -> int:
    """
    Write all tags to a UTF-8 CSV file at *path*.
    Columns:  TYP, TXPHEX, NAZOV, EPC_BITS, GROUP_IDX

    Compatible with any label printing system that accepts CSV databases,
    including Zebra ZebraDesigner, SATO CODETHINQ, and Honeywell Easycoder.

    Returns the total number of rows written (excluding header).
    """
    path  = Path(path)
    total = 0

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["TYP", "TXPHEX", "NAZOV", "EPC_BITS", "GROUP"])

        for g_idx, g in enumerate(groups, start=1):
            for tag in g.iter_tags():
                writer.writerow([
                    tag["TYP"],
                    tag["TXPHEX"],
                    tag["NAZOV"],
                    g.epc_bits,
                    g_idx,
                ])
                total += 1

    log.info("CSV exported: %s  (%d tags)", path, total)
    return total
