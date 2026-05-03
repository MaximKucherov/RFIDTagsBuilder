"""
RFIDTagBuilder v3 — EPC Business Logic
========================================
ASCII validation, CRC-16/CCITT-FALSE, duplicate detection, and project audit.
No UI imports — this module is pure logic, fully testable in isolation.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from models import TagGroup

log = logging.getLogger(__name__)

# ── Printable ASCII gate ─────────────────────────────────────────────────────────
# EPC Gen2 / ISO 18000-6C ASCII memory expects characters in range 0x20–0x7E.
_ASCII_RE = re.compile(r"^[\x20-\x7E]*$")


def validate_ascii_field(value: str, field_name: str) -> Optional[str]:
    """
    Return an error message string if *value* contains characters outside
    the printable ASCII range (0x20–0x7E).  Return None if the field is valid.
    """
    if not _ASCII_RE.match(value):
        bad = sorted({repr(c) for c in value if not (0x20 <= ord(c) <= 0x7E)})
        return (
            f"'{field_name}' contains characters outside printable ASCII "
            f"(0x20–0x7E): {', '.join(bad)}"
        )
    return None


# ── Single-group validation ──────────────────────────────────────────────────────

def validate_group(g: TagGroup) -> list[str]:
    """
    Validate one TagGroup and return a list of human-readable error strings.
    An empty list means the group is fully valid.
    """
    errors: list[str] = []

    for value, name in [
        (g.prefix, "Prefix"),
        (g.suffix, "Suffix"),
        (g.nazov,  "Description"),
    ]:
        err = validate_ascii_field(value, name)
        if err:
            errors.append(err)

    if g.has_overflow:
        used = len(g.prefix) + len(g.suffix) + g._ab_len
        errors.append(
            f"EPC overflow: Prefix + Suffix + A/B indicator = {used} chars, "
            f"but EPC {g.epc_bits} bits allows only {g.epc_ascii_chars} chars total. "
            f"Shorten the prefix/suffix or choose a larger EPC memory."
        )

    if g.counter_end < g.counter_start:
        errors.append("Counter End must be ≥ Counter Start.")

    if not g.has_overflow and g.counter_end > g.max_counter:
        errors.append(
            f"Counter End ({g.counter_end}) exceeds the maximum allowed value "
            f"({g.max_counter}) for a {g.counter_padding}-digit counter field. "
            f"Shorten the prefix or choose a larger EPC memory."
        )

    return errors


# ── CRC-16 / CCITT-FALSE ─────────────────────────────────────────────────────────

def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    """
    CRC-16/CCITT-FALSE — polynomial 0x1021, initial value 0xFFFF.

    This variant is used by EPC Gen2 (ISO 18000-6C) for PC+EPC word
    integrity verification in the RESERVED memory bank.
    """
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def epc_crc16(typ_string: str) -> str:
    """
    Compute the CRC-16/CCITT-FALSE of a TYP string and return it
    as a 4-character uppercase HEX value (e.g. "A3F2").
    """
    return f"{crc16_ccitt(typ_string.encode('ascii')):04X}"


# ── Duplicate detection ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DuplicateIssue:
    typ:    str   # The duplicated TYP value
    group1: str   # Label of the first group to generate this TYP
    group2: str   # Label of the second (conflicting) group


def find_duplicates(groups: list[TagGroup]) -> list[DuplicateIssue]:
    """
    Scan the full set of groups and return every TYP value that would
    appear more than once in the exported database.

    Groups with EPC overflow are skipped (they produce no valid tags).
    """
    seen:   dict[str, str]      = {}   # typ → first group label
    issues: list[DuplicateIssue] = []

    for g in groups:
        if g.has_overflow:
            continue
        label = g.nazov or g.prefix or "(unnamed)"
        for tag in g.iter_tags():
            typ = tag["TYP"]
            if typ in seen:
                issues.append(DuplicateIssue(typ=typ, group1=seen[typ], group2=label))
            else:
                seen[typ] = label

    return issues


# ── Project audit ────────────────────────────────────────────────────────────────

@dataclass
class AuditIssue:
    severity: str   # "ERROR" | "WARNING" | "INFO"
    group:    str   # Group label for display
    message:  str


_SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}


def audit_project(groups: list[TagGroup]) -> list[AuditIssue]:
    """
    Run a full pre-export audit across all groups.

    Checks performed:
    - Per-group ASCII validity, EPC overflow, counter range
    - Zero-tag groups
    - Missing descriptions
    - Cross-group duplicate TYP values

    Returns issues sorted ERROR → WARNING → INFO.
    """
    issues: list[AuditIssue] = []

    if not groups:
        issues.append(AuditIssue("WARNING", "Project", "No groups defined."))
        return issues

    for g in groups:
        label = g.nazov or g.prefix or "(unnamed)"

        for err in validate_group(g):
            issues.append(AuditIssue("ERROR", label, err))

        if g.count == 0:
            issues.append(AuditIssue("WARNING", label,
                "This group generates 0 tags (check counter range)."))

        if not g.nazov.strip():
            issues.append(AuditIssue("INFO", label,
                "Description (NAZOV) is empty — exported NAZOV column will be blank."))

    for dup in find_duplicates(groups):
        issues.append(AuditIssue(
            "ERROR", dup.group2,
            f"Duplicate TYP '{dup.typ}' — also generated by group '{dup.group1}'. "
            "The exported database will contain duplicate EPC records."
        ))

    issues.sort(key=lambda i: _SEVERITY_ORDER.get(i.severity, 9))
    log.debug("Audit complete: %d issues (%d errors)",
              len(issues),
              sum(1 for i in issues if i.severity == "ERROR"))
    return issues
