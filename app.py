"""
RFIDTagBuilder v3 — CustomTkinter UI
======================================
Modern dark/light-mode desktop interface.
Architecture: thin UI layer over models + epc_logic + export modules.
"""
from __future__ import annotations

import collections
import copy
import json
import logging
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import customtkinter as ctk

from epc_logic import (
    AuditIssue,
    audit_project,
    epc_crc16,
    validate_ascii_field,
    validate_group,
)
from export import export_csv, export_excel
from models import (
    APP_NAME,
    APP_VERSION,
    EPC_BITS_LIST,
    EPC_OPTIONS,
    GROUP_PALETTE_DARK,
    GROUP_PALETTE_LIGHT,
    TagGroup,
    ascii_to_hex,
)

log = logging.getLogger(__name__)

# ── Global CTk theme ─────────────────────────────────────────────────────────────
ctk.set_default_color_theme("blue")

# ── Colours (light / dark) ───────────────────────────────────────────────────────
THEME = {
    "Light": {
        "tv_bg":        "#FFFFFF",
        "tv_fg":        "#1A1A1A",
        "tv_sel":       "#1565C0",
        "tv_heading":   "#E8EEF7",
        "tv_heading_fg":"#1A1A1A",
        "status_bg":    "#E8EEF7",
    },
    "Dark": {
        "tv_bg":        "#2B2B2B",
        "tv_fg":        "#E0E0E0",
        "tv_sel":       "#1A5C9E",
        "tv_heading":   "#1E1E1E",
        "tv_heading_fg":"#CCCCCC",
        "status_bg":    "#1E1E1E",
    },
}


def _mode() -> str:
    return ctk.get_appearance_mode()   # "Light" or "Dark"


# ═══════════════════════════════════════════════════════════════════════════════
# GroupDialog — Add / Edit a TagGroup
# ═══════════════════════════════════════════════════════════════════════════════

class GroupDialog(ctk.CTkToplevel):
    """Modal dialog for adding or editing one TagGroup."""

    def __init__(self, parent: ctk.CTk, group: Optional[TagGroup] = None):
        super().__init__(parent)
        self.title("Edit Group" if group else "Add Group")
        self.resizable(False, False)
        self.result: Optional[TagGroup] = None
        self._src  = group.copy() if group else TagGroup()
        self._build()
        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.wait_window()

    # ── Build ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        g   = self._src
        PAD = {"padx": 12, "pady": 6}

        outer = ctk.CTkFrame(self, corner_radius=0)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        # ── Description ──────────────────────────────────────────────────────
        ctk.CTkLabel(outer, text="Description (NAZOV):", anchor="w").grid(
            row=0, column=0, sticky="w", **PAD)
        self._nazov = ctk.CTkEntry(outer, width=340)
        self._nazov.insert(0, g.nazov)
        self._nazov.grid(row=0, column=1, columnspan=3, sticky="ew", **PAD)

        # ── Prefix / Suffix ───────────────────────────────────────────────────
        ctk.CTkLabel(outer, text="Prefix:", anchor="w").grid(
            row=1, column=0, sticky="w", **PAD)
        self._prefix = ctk.CTkEntry(outer, width=180)
        self._prefix.insert(0, g.prefix)
        self._prefix.grid(row=1, column=1, sticky="ew", **PAD)

        ctk.CTkLabel(outer, text="Suffix:", anchor="w").grid(
            row=1, column=2, sticky="w", **PAD)
        self._suffix = ctk.CTkEntry(outer, width=100)
        self._suffix.insert(0, g.suffix)
        self._suffix.grid(row=1, column=3, sticky="ew", **PAD)

        # ── EPC Memory ────────────────────────────────────────────────────────
        ctk.CTkLabel(outer, text="EPC Memory:", anchor="w").grid(
            row=2, column=0, sticky="w", **PAD)

        epc_row = ctk.CTkFrame(outer, fg_color="transparent")
        epc_row.grid(row=2, column=1, columnspan=3, sticky="w", **PAD)

        self._epc_var = ctk.StringVar(value=f"{g.epc_bits} bits")
        self._epc_combo = ctk.CTkComboBox(
            epc_row,
            values=[f"{b} bits" for b in EPC_BITS_LIST],
            variable=self._epc_var,
            width=130,
            command=lambda _: self._update_preview(),
        )
        self._epc_combo.pack(side="left")

        self._epc_info = ctk.CTkLabel(epc_row, text="", text_color="gray",
                                      font=ctk.CTkFont(size=11))
        self._epc_info.pack(side="left", padx=(12, 0))

        # ── Counter range ─────────────────────────────────────────────────────
        ctk.CTkLabel(outer, text="Counter Start:", anchor="w").grid(
            row=3, column=0, sticky="w", **PAD)
        self._cstart = ctk.CTkEntry(outer, width=90)
        self._cstart.insert(0, str(g.counter_start))
        self._cstart.grid(row=3, column=1, sticky="w", **PAD)

        ctk.CTkLabel(outer, text="Counter End:", anchor="w").grid(
            row=3, column=2, sticky="w", **PAD)
        self._cend = ctk.CTkEntry(outer, width=90)
        self._cend.insert(0, str(g.counter_end))
        self._cend.grid(row=3, column=3, sticky="w", **PAD)

        # ── A/B options ───────────────────────────────────────────────────────
        self._ab_var = ctk.BooleanVar(value=g.ab_pair)
        ctk.CTkCheckBox(outer, text="Generate A/B paired tags",
                        variable=self._ab_var,
                        command=self._update_preview).grid(
            row=4, column=0, columnspan=2, sticky="w", **PAD)

        self._ab_grouped_var = ctk.BooleanVar(value=g.ab_grouped)
        ctk.CTkCheckBox(outer, text="Grouped order  (all A → all B)",
                        variable=self._ab_grouped_var).grid(
            row=4, column=2, columnspan=2, sticky="w", **PAD)

        # ── Separator ─────────────────────────────────────────────────────────
        ttk.Separator(outer, orient="horizontal").grid(
            row=5, column=0, columnspan=4, sticky="ew", pady=8, padx=12)

        # ── Live preview labels ───────────────────────────────────────────────
        def _pl(row: int, lbl: str, attr: str, fg: str = "gray") -> ctk.CTkLabel:
            ctk.CTkLabel(outer, text=lbl, anchor="w").grid(
                row=row, column=0, sticky="w", **PAD)
            widget = ctk.CTkLabel(outer, text="", anchor="w",
                                  text_color=fg,
                                  font=ctk.CTkFont(family="Courier New", size=11),
                                  width=420)
            widget.grid(row=row, column=1, columnspan=3, sticky="w", **PAD)
            setattr(self, attr, widget)
            return widget

        _pl(6, "Tag preview:",  "_prev_typ",  "#1565C0")
        _pl(7, "HEX preview:",  "_prev_hex",  "gray")
        _pl(8, "CRC-16 (EPC):", "_prev_crc",  "gray")

        ctk.CTkLabel(outer, text="EPC status:", anchor="w").grid(
            row=9, column=0, sticky="w", **PAD)
        self._prev_epc = ctk.CTkLabel(outer, text="", anchor="w",
                                      font=ctk.CTkFont(size=11, weight="bold"), width=420)
        self._prev_epc.grid(row=9, column=1, columnspan=3, sticky="w", **PAD)

        ctk.CTkLabel(outer, text="Tag count:", anchor="w").grid(
            row=10, column=0, sticky="w", **PAD)
        self._prev_cnt = ctk.CTkLabel(outer, text="",
                                      font=ctk.CTkFont(size=11, weight="bold"),
                                      text_color="#2E7D32")
        self._prev_cnt.grid(row=10, column=1, sticky="w", **PAD)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.grid(row=11, column=0, columnspan=4, pady=(14, 0))
        ctk.CTkButton(btn_row, text="  Save  ", command=self._ok,
                      width=120).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancel", command=self.destroy,
                      fg_color="gray40", hover_color="gray30",
                      width=100).pack(side="left", padx=8)

        # ── Live-update bindings ──────────────────────────────────────────────
        for widget in (self._prefix, self._suffix, self._nazov,
                       self._cstart, self._cend):
            widget.bind("<KeyRelease>", lambda _e: self._update_preview())
        self._ab_var.trace_add("write", lambda *_: self._update_preview())

        self._update_preview()

    # ── Live preview ─────────────────────────────────────────────────────────

    def _current_epc_bits(self) -> int:
        try:
            return int(self._epc_var.get().split()[0])
        except (ValueError, AttributeError):
            return 128

    def _update_preview(self) -> None:
        try:
            epc_bits  = self._current_epc_bits()
            epc_ascii = EPC_OPTIONS[epc_bits]["ascii"]
            epc_hex   = EPC_OPTIONS[epc_bits]["hex"]
            pref      = self._prefix.get()
            suf       = self._suffix.get()
            ab        = self._ab_var.get()
            ab_len    = 1 if ab else 0
            available = epc_ascii - len(pref) - len(suf) - ab_len
            pad       = max(1, available)
            max_ctr   = 10 ** pad - 1

            try:
                start = int(self._cstart.get())
                end   = int(self._cend.get())
            except ValueError:
                start = end = 1

            self._epc_info.configure(
                text=f"→  {epc_ascii} ASCII  ·  {epc_hex} HEX chars"
            )

            c    = str(start).zfill(pad)
            base = f"{pref}{c}{suf}"

            if ab:
                typ_str = f"{base}A   /   {base}B"
                hex_str = f"{ascii_to_hex(base + 'A')}  /  {ascii_to_hex(base + 'B')}"
                crc_str = f"{epc_crc16(base + 'A')}  /  {epc_crc16(base + 'B')}"
            else:
                typ_str = base
                hex_str = ascii_to_hex(base)
                crc_str = epc_crc16(base)

            n = max(0, end - start + 1) * (2 if ab else 1)

            self._prev_typ.configure(text=typ_str)
            self._prev_hex.configure(text=hex_str)
            self._prev_crc.configure(text=crc_str)
            self._prev_cnt.configure(text=f"{n} tags")

            # EPC status colour
            tag_len = len(pref) + pad + len(suf) + ab_len
            if available < 1:
                msg   = (f"  OVERFLOW — Prefix+Suffix+A/B = {len(pref)+len(suf)+ab_len} chars"
                         f" > EPC {epc_bits} bit ({epc_ascii} chars)")
                color = "#C62828"
            elif end > max_ctr:
                msg   = (f"  COUNTER OVERFLOW — max value = {max_ctr}"
                         f"  ({pad} digit{'s' if pad != 1 else ''} available)")
                color = "#C62828"
            else:
                msg   = (f"  OK — {tag_len} chars = {epc_bits} bits"
                         f"  |  counter: {pad} digit{'s' if pad != 1 else ''},"
                         f"  max {max_ctr}")
                color = "#2E7D32"

            self._prev_epc.configure(text=msg, text_color=color)

        except Exception:
            pass   # silent: keep existing preview text on any transient parse error

    # ── OK / Save ────────────────────────────────────────────────────────────

    def _ok(self) -> None:
        pref = self._prefix.get()
        suf  = self._suffix.get()
        nazov = self._nazov.get().strip()

        # ASCII field validation
        for val, name in [(pref, "Prefix"), (suf, "Suffix"), (nazov, "Description")]:
            err = validate_ascii_field(val, name)
            if err:
                messagebox.showerror("Invalid Characters", err, parent=self)
                return

        try:
            start    = int(self._cstart.get())
            end      = int(self._cend.get())
            epc_bits = self._current_epc_bits()
        except ValueError:
            messagebox.showerror("Invalid Input",
                                 "Counter Start and End must be integers.", parent=self)
            return

        if end < start:
            messagebox.showerror("Invalid Range",
                                 "Counter End must be ≥ Counter Start.", parent=self)
            return

        candidate = TagGroup(
            nazov=nazov, prefix=pref, suffix=suf,
            counter_start=start, counter_end=end,
            epc_bits=epc_bits,
            ab_pair=self._ab_var.get(),
            ab_grouped=self._ab_grouped_var.get(),
        )

        errs = validate_group(candidate)
        if errs:
            messagebox.showerror("Validation Error", "\n\n".join(errs), parent=self)
            return

        self.result = candidate
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
# AuditDialog — Project Audit Results
# ═══════════════════════════════════════════════════════════════════════════════

class AuditDialog(ctk.CTkToplevel):
    """Read-only dialog displaying the results of audit_project()."""

    _ICONS = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}
    _COLORS = {"ERROR": "#C62828", "WARNING": "#E65100", "INFO": "#1565C0"}

    def __init__(self, parent: ctk.CTk, issues: list[AuditIssue]):
        super().__init__(parent)
        self.title("Project Audit Report")
        self.geometry("700x460")
        self.resizable(True, True)
        self._build(issues)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

    def _build(self, issues: list[AuditIssue]) -> None:
        errors   = sum(1 for i in issues if i.severity == "ERROR")
        warnings = sum(1 for i in issues if i.severity == "WARNING")

        # Summary bar
        summary_color = "#C62828" if errors else ("#E65100" if warnings else "#2E7D32")
        summary_text  = (
            f"  {errors} error(s)  ·  {warnings} warning(s)"
            if issues else "  ✓  No issues found — project is ready for export."
        )
        ctk.CTkLabel(self, text=summary_text, text_color=summary_color,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(12, 4))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=12, pady=2)

        # Scrollable issue list
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=12, pady=8)

        if not issues:
            ctk.CTkLabel(scroll, text="All groups passed validation.",
                         text_color="gray").pack(pady=20)
        else:
            for iss in issues:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=3)

                icon_lbl = ctk.CTkLabel(
                    row,
                    text=self._ICONS.get(iss.severity, "•"),
                    width=28, anchor="center",
                    font=ctk.CTkFont(size=13),
                )
                icon_lbl.pack(side="left")

                group_lbl = ctk.CTkLabel(
                    row,
                    text=f"[{iss.group}]",
                    text_color=self._COLORS.get(iss.severity, "gray"),
                    font=ctk.CTkFont(size=11, weight="bold"),
                    width=140, anchor="w",
                )
                group_lbl.pack(side="left", padx=(4, 8))

                msg_lbl = ctk.CTkLabel(
                    row, text=iss.message, anchor="w",
                    font=ctk.CTkFont(size=11),
                    wraplength=440,
                )
                msg_lbl.pack(side="left", fill="x")

        # Close button
        ctk.CTkButton(self, text="Close", command=self.destroy,
                      width=100).pack(pady=(4, 12))


# ═══════════════════════════════════════════════════════════════════════════════
# Main Application Window
# ═══════════════════════════════════════════════════════════════════════════════

class App:
    """
    RFIDTagBuilder main window.

    State:
        self.groups      — canonical list of TagGroup objects
        self._history    — deque of deep-copied states for Undo
        self._future     — deque of deep-copied states for Redo
        self._project    — current .rfid file path (None = unsaved)
        self._dirty      — unsaved changes flag
    """

    _HISTORY_LIMIT = 50

    def __init__(self) -> None:
        self.groups:   list[TagGroup] = []
        self._history: collections.deque = collections.deque(maxlen=self._HISTORY_LIMIT)
        self._future:  collections.deque = collections.deque(maxlen=self._HISTORY_LIMIT)
        self._project: Optional[str] = None
        self._dirty   = False

        ctk.set_appearance_mode("Dark")

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME}  v{APP_VERSION}")
        self.root.geometry("1480x800")
        self.root.minsize(1000, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._apply_treeview_theme()
        self._refresh()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_content()
        self._build_statusbar()

    def _build_toolbar(self) -> None:
        tb = ctk.CTkFrame(self.root, corner_radius=0, height=48)
        tb.grid(row=0, column=0, sticky="ew")
        tb.grid_propagate(False)

        def btn(text: str, cmd, width: int = 0, color: str | None = None):
            kw: dict = {"text": text, "command": cmd, "height": 32}
            if width:
                kw["width"] = width
            if color:
                kw["fg_color"] = color
            return ctk.CTkButton(tb, **kw)

        def sep():
            ctk.CTkLabel(tb, text="|", text_color="gray40", width=8).pack(
                side="left", padx=2, pady=8)

        # Group actions
        btn("＋  Add",    self._add,    width=90).pack(side="left", padx=(8, 2), pady=8)
        btn("✎  Edit",   self._edit,   width=80).pack(side="left", padx=2,      pady=8)
        btn("✕  Delete", self._delete, width=90,
            color="#8B2020").pack(side="left", padx=2, pady=8)
        sep()

        # Order
        btn("▲ Up",   self._move_up,   width=70).pack(side="left", padx=2, pady=8)
        btn("▼ Down", self._move_down, width=80).pack(side="left", padx=2, pady=8)
        sep()

        # Undo / Redo
        btn("↩ Undo", self._undo, width=80).pack(side="left", padx=2, pady=8)
        btn("↪ Redo", self._redo, width=80).pack(side="left", padx=2, pady=8)
        sep()

        # Project
        btn("💾 Save",    self._save,    width=80).pack(side="left", padx=2, pady=8)
        btn("📂 Load",    self._load,    width=80).pack(side="left", padx=2, pady=8)
        sep()

        # Export
        btn("📊 Excel",  self._export_excel, width=90,
            color="#1E6B1E").pack(side="left", padx=2, pady=8)
        btn("📄 CSV",    self._export_csv,   width=80,
            color="#1E6B1E").pack(side="left", padx=2, pady=8)
        sep()

        # Audit
        btn("🔍 Audit", self._run_audit, width=90,
            color="#6B4E1E").pack(side="left", padx=2, pady=8)
        sep()

        # Demo preset
        btn("⚡ Demo",  self._load_demo, width=80,
            color="#444").pack(side="left", padx=2, pady=8)

        # Right: theme toggle
        self._theme_btn = ctk.CTkButton(
            tb, text="☀ Light", command=self._toggle_theme,
            width=90, height=32, fg_color="gray30", hover_color="gray20",
        )
        self._theme_btn.pack(side="right", padx=8, pady=8)

    def _build_content(self) -> None:
        pane = tk.PanedWindow(self.root, orient="horizontal",
                              sashwidth=6, sashrelief="flat",
                              bg="#1A1A1A")
        pane.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))

        # ── Left: Group list ─────────────────────────────────────────────────
        left_frame = ctk.CTkFrame(pane, corner_radius=6)
        pane.add(left_frame, width=560, minsize=400)
        left_frame.grid_rowconfigure(0, weight=0)
        left_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left_frame, text="  Tag Groups",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=2,
                                      sticky="w", padx=8, pady=(6, 2))

        g_cols   = ("Description", "Prefix", "EPC", "Range", "A/B", "Tags")
        self._gtree = ttk.Treeview(left_frame, columns=g_cols,
                                   show="headings", height=28,
                                   selectmode="browse", style="Custom.Treeview")
        _gw = [148, 100, 60, 120, 40, 50]
        for col, w in zip(g_cols, _gw):
            self._gtree.heading(col, text=col)
            self._gtree.column(col, width=w, minwidth=30,
                               anchor="w" if col in ("Description", "Prefix") else "center")

        self._gtree.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb_l = ttk.Scrollbar(left_frame, orient="vertical",
                             command=self._gtree.yview, style="Custom.Vertical.TScrollbar")
        sb_l.grid(row=1, column=1, sticky="ns", pady=6)
        self._gtree.configure(yscrollcommand=sb_l.set)
        self._gtree.bind("<Double-1>", lambda _: self._edit())
        left_frame.grid_rowconfigure(1, weight=1)

        # ── Right: Tag preview ───────────────────────────────────────────────
        right_frame = ctk.CTkFrame(pane, corner_radius=6)
        pane.add(right_frame, minsize=500)
        right_frame.grid_rowconfigure(0, weight=0)
        right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right_frame, text="  Generated Tags Preview",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=2,
                                      sticky="w", padx=8, pady=(6, 2))

        p_cols = ("#", "TYP", "TXPHEX", "CRC-16", "NAZOV")
        self._ptree = ttk.Treeview(right_frame, columns=p_cols,
                                   show="headings", height=28,
                                   selectmode="none", style="Custom.Treeview")
        _pw = [46, 210, 360, 68, 200]
        for col, w in zip(p_cols, _pw):
            self._ptree.heading(col, text=col)
            self._ptree.column(col, width=w, minwidth=30,
                               anchor="center" if col in ("#", "CRC-16") else "w")

        self._ptree.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb_r = ttk.Scrollbar(right_frame, orient="vertical",
                             command=self._ptree.yview, style="Custom.Vertical.TScrollbar")
        sb_r.grid(row=1, column=1, sticky="ns", pady=6)
        self._ptree.configure(yscrollcommand=sb_r.set)
        right_frame.grid_rowconfigure(1, weight=1)

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self.root, corner_radius=0, height=28)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)

        self._sv_total = ctk.StringVar(value="Ready")
        ctk.CTkLabel(bar, textvariable=self._sv_total,
                     font=ctk.CTkFont(size=11),
                     anchor="w").pack(side="left", padx=10)

    # ── Treeview theme ────────────────────────────────────────────────────────

    def _apply_treeview_theme(self) -> None:
        mode = _mode()
        t    = THEME.get(mode, THEME["Dark"])
        s    = ttk.Style()

        s.configure("Custom.Treeview",
                    background=t["tv_bg"], foreground=t["tv_fg"],
                    fieldbackground=t["tv_bg"],
                    font=("Arial", 9), rowheight=22)
        s.map("Custom.Treeview",
              background=[("selected", t["tv_sel"])],
              foreground=[("selected", "#FFFFFF")])
        s.configure("Custom.Treeview.Heading",
                    background=t["tv_heading"], foreground=t["tv_heading_fg"],
                    font=("Arial", 9, "bold"), relief="flat")
        s.configure("Custom.Vertical.TScrollbar",
                    background=t["tv_heading"], troughcolor=t["tv_bg"],
                    arrowcolor=t["tv_fg"])

    # ── Theme toggle ──────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        new_mode = "Light" if _mode() == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        self._theme_btn.configure(
            text="☀ Light" if new_mode == "Dark" else "🌙 Dark"
        )
        self._apply_treeview_theme()
        self._refresh()   # re-paint row colours

    # ── State management / Undo-Redo ──────────────────────────────────────────

    def _push_history(self) -> None:
        self._history.append(copy.deepcopy(self.groups))
        self._future.clear()
        self._dirty = True

    def _undo(self) -> None:
        if not self._history:
            return
        self._future.append(copy.deepcopy(self.groups))
        self.groups = self._history.pop()
        self._refresh()

    def _redo(self) -> None:
        if not self._future:
            return
        self._history.append(copy.deepcopy(self.groups))
        self.groups = self._future.pop()
        self._refresh()

    # ── Group CRUD ────────────────────────────────────────────────────────────

    def _add(self) -> None:
        dlg = GroupDialog(self.root)
        if dlg.result:
            self._push_history()
            self.groups.append(dlg.result)
            self._refresh()

    def _edit(self) -> None:
        sel = self._gtree.selection()
        if not sel:
            messagebox.showinfo("Select Group", "Please select a group to edit.")
            return
        idx = self._gtree.index(sel[0])
        dlg = GroupDialog(self.root, self.groups[idx])
        if dlg.result:
            self._push_history()
            self.groups[idx] = dlg.result
            self._refresh()

    def _delete(self) -> None:
        sel = self._gtree.selection()
        if not sel:
            return
        idx  = self._gtree.index(sel[0])
        name = self.groups[idx].nazov or self.groups[idx].prefix or "this group"
        if messagebox.askyesno("Delete Group", f"Delete '{name}'?"):
            self._push_history()
            self.groups.pop(idx)
            self._refresh()

    def _move_up(self) -> None:
        sel = self._gtree.selection()
        if not sel:
            return
        idx = self._gtree.index(sel[0])
        if idx > 0:
            self._push_history()
            self.groups[idx], self.groups[idx - 1] = self.groups[idx - 1], self.groups[idx]
            self._refresh()
            self._gtree.selection_set(self._gtree.get_children()[idx - 1])

    def _move_down(self) -> None:
        sel = self._gtree.selection()
        if not sel:
            return
        idx = self._gtree.index(sel[0])
        if idx < len(self.groups) - 1:
            self._push_history()
            self.groups[idx], self.groups[idx + 1] = self.groups[idx + 1], self.groups[idx]
            self._refresh()
            self._gtree.selection_set(self._gtree.get_children()[idx + 1])

    # ── Refresh display ───────────────────────────────────────────────────────

    def _refresh(self) -> None:
        palette = (GROUP_PALETTE_DARK if _mode() == "Dark"
                   else GROUP_PALETTE_LIGHT)

        # Group list
        self._gtree.delete(*self._gtree.get_children())
        for g in self.groups:
            pad = g.counter_padding
            rng = (f"{str(g.counter_start).zfill(pad)}"
                   f" – {str(g.counter_end).zfill(pad)}")
            self._gtree.insert("", "end", values=(
                g.nazov, g.prefix,
                f"{g.epc_bits} bit", rng,
                "A/B" if g.ab_pair else "–",
                g.count,
            ))

        # Tag preview (with CRC-16 column)
        self._ptree.delete(*self._ptree.get_children())
        row_n = 0
        for g_idx, g in enumerate(self.groups):
            bg = palette[g_idx % len(palette)]
            tag_list = g.generate()
            for tag in tag_list:
                row_n += 1
                crc = epc_crc16(tag["TYP"])
                iid = self._ptree.insert("", "end", values=(
                    row_n, tag["TYP"], tag["TXPHEX"], crc, tag["NAZOV"]
                ))
                self._ptree.tag_configure(f"g{g_idx}", background=bg)
                self._ptree.item(iid, tags=(f"g{g_idx}",))

        total  = sum(g.count for g in self.groups)
        groups = len(self.groups)
        proj   = Path(self._project).name if self._project else "unsaved"
        self._sv_total.set(
            f"  Groups: {groups}  ·  Total tags: {total}  ·  Project: {proj}"
        )

    # ── Save / Load ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".rfid",
            filetypes=[("RFID Project", "*.rfid"), ("All Files", "*.*")],
            initialfile=Path(self._project or "project.rfid").name,
            title="Save Project",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([g.to_dict() for g in self.groups], f,
                          indent=2, ensure_ascii=False)
            self._project = path
            self._dirty   = False
            self._refresh()
            messagebox.showinfo("Saved", f"Project saved:\n{path}")
        except OSError as exc:
            messagebox.showerror("Save Error", str(exc))

    def _load(self) -> None:
        if self._dirty:
            if not messagebox.askyesno("Unsaved Changes",
                                       "Discard unsaved changes and load a project?"):
                return
        path = filedialog.askopenfilename(
            filetypes=[("RFID Project", "*.rfid"), ("All Files", "*.*")],
            title="Load Project",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._push_history()
            self.groups   = [TagGroup.from_dict(d) for d in data]
            self._project = path
            self._dirty   = False
            self._refresh()
        except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
            messagebox.showerror("Load Error", f"Cannot load project:\n{exc}")

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_excel(self) -> None:
        if not self.groups:
            messagebox.showwarning("No Data", "Add at least one group before exporting.")
            return
        self._pre_export_audit_check()
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel Workbook", "*.xlsx")],
            initialfile="RFID_Tags_Database.xlsx",
            title="Export to Excel",
        )
        if not path:
            return
        try:
            total = export_excel(self.groups, path)
            messagebox.showinfo("Export Complete",
                                f"Exported {total} tags to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))
            log.exception("Excel export failed")

    def _export_csv(self) -> None:
        if not self.groups:
            messagebox.showwarning("No Data", "Add at least one group before exporting.")
            return
        self._pre_export_audit_check()
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv")],
            initialfile="RFID_Tags_Database.csv",
            title="Export to CSV",
        )
        if not path:
            return
        try:
            total = export_csv(self.groups, path)
            messagebox.showinfo("Export Complete",
                                f"Exported {total} tags to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))
            log.exception("CSV export failed")

    def _pre_export_audit_check(self) -> None:
        """Warn about errors before export; let the user cancel if needed."""
        issues  = audit_project(self.groups)
        errors  = [i for i in issues if i.severity == "ERROR"]
        if errors:
            proceed = messagebox.askyesno(
                "Audit Warnings",
                f"The project has {len(errors)} error(s) that may cause "
                "data integrity issues in the exported file.\n\n"
                "Run a full audit (recommended) or export anyway?",
                icon="warning",
            )
            if not proceed:
                self._run_audit()

    # ── Project Audit ─────────────────────────────────────────────────────────

    def _run_audit(self) -> None:
        issues = audit_project(self.groups)
        AuditDialog(self.root, issues)

    # ── Demo preset ───────────────────────────────────────────────────────────

    def _load_demo(self) -> None:
        if self.groups:
            if not messagebox.askyesno(
                "Load Demo",
                "This will replace the current project with the demo preset.\n"
                "Continue?"
            ):
                return
        # 128-bit EPC demo: "PrefixName" (9-10 chars) + counter + "A"/"B" = 16 chars
        self._push_history()
        self.groups = [
            TagGroup("MINI SIDE PANEL", "SidPanMin", "", 1, 20,  128, True),
            TagGroup("SIDE PANEL",      "SidPanLon", "", 1, 80,  128, True),
            TagGroup("LONG PLATFORM",   "PlatLong",  "", 1, 40,  128, True),
            TagGroup("EURO PLATFORM",   "PlatShort", "", 1, 20,  128, True),
            TagGroup("XL PLATFORM",     "PlatXtLrg", "", 1, 20,  128, True),
        ]
        self._project = None
        self._dirty   = True
        self._refresh()

    # ── Close guard ───────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self._dirty:
            if not messagebox.askyesno("Unsaved Changes",
                                       "You have unsaved changes.\nExit anyway?"):
                return
        self.root.destroy()

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.root.mainloop()
