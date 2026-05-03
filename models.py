"""
RFIDTagBuilder v3 — Data Models
================================
EPC memory constants, ascii_to_hex encoder, and the TagGroup dataclass.
All business rules live here; the UI layer never touches raw bytes.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Iterator

# ── Application metadata ────────────────────────────────────────────────────────
APP_NAME    = "RFIDTagBuilder"
APP_VERSION = "3.0.0"

# ── EPC memory table ─────────────────────────────────────────────────────────────
# Maps EPC size in bits → {ascii character capacity, hex character width}
EPC_OPTIONS: dict[int, dict[str, int]] = {
     96: {"ascii": 12,  "hex": 24},
    128: {"ascii": 16,  "hex": 32},
    192: {"ascii": 24,  "hex": 48},
    256: {"ascii": 32,  "hex": 64},
    496: {"ascii": 62,  "hex": 124},
}
EPC_BITS_LIST: list[int] = sorted(EPC_OPTIONS)

# ── Row colour palettes ──────────────────────────────────────────────────────────
GROUP_PALETTE_LIGHT: list[str] = [
    "#FFFFFF", "#EEF4FF", "#FFF8EE", "#EEFFF2",
    "#FFF0F0", "#F5EEFF", "#FFFFF0", "#EEF8FF",
]
GROUP_PALETTE_DARK: list[str] = [
    "#2B2B2B", "#1E2D42", "#2D2418", "#182D1E",
    "#2D1818", "#261826", "#2B2B18", "#182B2D",
]


# ── Core encoder ─────────────────────────────────────────────────────────────────

def ascii_to_hex(text: str) -> str:
    """Encode ASCII text to an uppercase HEX string (2 hex chars per byte)."""
    return "".join(f"{ord(c):02X}" for c in text)


def hex_to_ascii(hex_str: str) -> str:
    """Decode a HEX string back to ASCII.  Returns '<invalid>' on failure."""
    try:
        return bytes.fromhex(hex_str).decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return "<invalid>"


# ── TagGroup ─────────────────────────────────────────────────────────────────────

@dataclass
class TagGroup:
    """
    One logical group of RFID tags sharing a prefix, suffix,
    counter range, and EPC memory configuration.

    Tag format:  {prefix}{counter_zero_padded}{suffix}{A|B}
    Counter padding is auto-calculated from EPC capacity.
    """

    nazov:         str  = ""     # Human-readable label / location name
    prefix:        str  = ""     # Fixed leading string  (e.g. "SidPanMin")
    suffix:        str  = ""     # Fixed trailing string (optional)
    counter_start: int  = 1
    counter_end:   int  = 10
    epc_bits:      int  = 128    # EPC memory size in bits
    ab_pair:       bool = True   # Generate paired A / B tags
    ab_grouped:    bool = True   # True = all A then all B; False = interleaved

    # ── EPC-derived properties ────────────────────────────────────────────────

    @property
    def epc_ascii_chars(self) -> int:
        """Total character capacity of this EPC memory size."""
        return EPC_OPTIONS[self.epc_bits]["ascii"]

    @property
    def epc_hex_chars(self) -> int:
        """Total HEX character width of this EPC memory size."""
        return EPC_OPTIONS[self.epc_bits]["hex"]

    @property
    def _ab_len(self) -> int:
        return 1 if self.ab_pair else 0

    @property
    def counter_padding(self) -> int:
        """
        Zero-padding width for the counter field.
        Automatically derived so that the full tag string exactly fills
        the EPC ASCII capacity.
        """
        available = (
            self.epc_ascii_chars
            - len(self.prefix)
            - len(self.suffix)
            - self._ab_len
        )
        return max(1, available)

    @property
    def max_counter(self) -> int:
        """Maximum allowed counter value for the current padding width."""
        return 10 ** self.counter_padding - 1

    @property
    def has_overflow(self) -> bool:
        """True when prefix + suffix + A/B indicator exceed EPC capacity."""
        available = (
            self.epc_ascii_chars
            - len(self.prefix)
            - len(self.suffix)
            - self._ab_len
        )
        return available < 1

    @property
    def count(self) -> int:
        """Total number of tags this group will generate."""
        n = max(0, self.counter_end - self.counter_start + 1)
        return n * 2 if self.ab_pair else n

    # ── Tag generation ────────────────────────────────────────────────────────

    def preview_typ(self) -> str:
        """Return a representative TYP string for live preview in the UI."""
        c    = str(self.counter_start).zfill(self.counter_padding)
        base = f"{self.prefix}{c}{self.suffix}"
        return f"{base}A  /  {base}B" if self.ab_pair else base

    def iter_tags(self) -> Iterator[dict[str, str]]:
        """Yield tag records: {"TYP": ..., "TXPHEX": ..., "NAZOV": ...}."""
        nums  = range(self.counter_start, self.counter_end + 1)
        sides = ["A", "B"] if self.ab_pair else [""]

        if self.ab_pair and self.ab_grouped:
            order = [(i, s) for s in sides for i in nums]
        else:
            order = [(i, s) for i in nums for s in sides]

        for i, s in order:
            c   = str(i).zfill(self.counter_padding)
            typ = f"{self.prefix}{c}{self.suffix}{s}"
            yield {"TYP": typ, "TXPHEX": ascii_to_hex(typ), "NAZOV": self.nazov}

    def generate(self) -> list[dict[str, str]]:
        """Return all tags as a materialised list."""
        return list(self.iter_tags())

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "nazov":         self.nazov,
            "prefix":        self.prefix,
            "suffix":        self.suffix,
            "counter_start": self.counter_start,
            "counter_end":   self.counter_end,
            "epc_bits":      self.epc_bits,
            "ab_pair":       self.ab_pair,
            "ab_grouped":    self.ab_grouped,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TagGroup":
        data = dict(d)
        # Migrate v1.x files that stored counter_padding instead of epc_bits
        if "counter_padding" in data and "epc_bits" not in data:
            data.pop("counter_padding")
            data.setdefault("epc_bits", 128)
        elif "counter_padding" in data:
            data.pop("counter_padding")
        valid_keys = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in valid_keys})

    def copy(self) -> "TagGroup":
        return copy.deepcopy(self)
