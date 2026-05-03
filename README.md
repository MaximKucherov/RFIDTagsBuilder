# RFIDTagBuilder

**Universal EPC Tag Database Generator for Industrial RFID Deployments**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey)](https://github.com/MaximKucherov/RFIDTagBuilder/releases)

---

## The Problem

Encoding thousands of RFID tags manually is an engineering bottleneck.

Every EPC Gen2 tag stores its identifier as a fixed-width HEX string in memory — 24 to 124 characters, depending on the chip. Translating human-readable location names (`SidPanMin0001A`) into the correct HEX encoding by hand, while managing prefix/suffix lengths, zero-padding, counter ranges, and A/B pairs across multiple tag groups, is tedious and error-prone.

One wrong character propagates silently through the entire database. The printer encodes thousands of tags. The error surfaces during inventory — not at generation time.

**RFIDTagBuilder eliminates this class of error entirely.**

---

## What It Does

RFIDTagBuilder is a desktop application that:

- Converts structured ASCII tag identifiers to compliant HEX EPC codes automatically
- Validates all fields against EPC memory constraints before generating any output
- Computes CRC-16/CCITT-FALSE checksums for EPC Gen2 integrity verification
- Detects duplicate TYP values across groups before export
- Exports a ready-to-import database in Excel (.xlsx) and CSV (.csv) formats

The output is compatible with **any** industrial label printing system that accepts
variable-data databases: Loftware (NiceLabel), Zebra ZebraDesigner, SATO CODETHINQ,
Honeywell Easycoder, and others.

---

## Tag Format

```
┌──────────────────────────────────────────────────────────────┐
│  EPC Memory  (e.g. 128 bits = 16 ASCII chars = 32 HEX chars) │
│                                                              │
│  ┌─────────┬──────────────┬────────┬───┐                     │
│  │ PREFIX  │   COUNTER    │ SUFFIX │A/B│                     │
│  │ static  │ zero-padded  │ static │   │                     │
│  └─────────┴──────────────┴────────┴───┘                     │
│   e.g.:                                                      │
│   "SidPanMin"  +  "000001"  +  ""  +  "A"  =  16 chars      │
│   → HEX: 5369645061...                 → 32 hex chars        │
└──────────────────────────────────────────────────────────────┘
```

**Counter padding is auto-calculated:**
`padding = EPC_ascii_capacity − len(prefix) − len(suffix) − ab_indicator`

**Supported EPC memory sizes:**

| Bits | ASCII capacity | HEX width |
|-----:|---------------:|----------:|
|   96 |           12   |        24 |
|  128 |           16   |        32 |
|  192 |           24   |        48 |
|  256 |           32   |        64 |
|  496 |           62   |       124 |

---

## Features

### Core
- ✅ ASCII → HEX encoding with strict printable-ASCII validation (0x20–0x7E)
- ✅ Real-time EPC overflow detection with actionable error messages
- ✅ CRC-16/CCITT-FALSE display for EPC Gen2 compliance verification
- ✅ A/B paired tag generation — interleaved or grouped order
- ✅ Multiple tag groups per project, each with independent configuration

### Data Integrity
- ✅ Pre-export Project Audit — catches errors before they reach the printer
- ✅ Duplicate TYP detection across all groups
- ✅ Counter overflow guard with suggested remediation
- ✅ Non-ASCII character rejection with specific character identification

### Workflow
- ✅ Save / Load projects in `.rfid` format (human-readable JSON)
- ✅ Undo / Redo for all group operations (50-step history)
- ✅ Excel export (two sheets: full database + summary with totals)
- ✅ CSV export for universal compatibility
- ✅ Dark / Light mode with one click

---

## Installation

### Option A — Pre-built Windows executable (no Python required)

Download `RFIDTagBuilder.exe` from the [Releases](https://github.com/MaximKucherov/RFIDTagBuilder/releases) page. No installation needed.

### Option B — Run from source

```bash
# Python 3.10 or newer required
git clone https://github.com/MaximKucherov/RFIDTagBuilder.git
cd RFIDTagBuilder

pip install -r requirements.txt
python main.py
```

### Option C — Build the executable yourself

```bash
pip install pyinstaller
build.bat       # Windows
```

Output: `dist/RFIDTagBuilder.exe`

---

## Quick Start

1. Click **＋ Add** to create a tag group
2. Set a prefix (e.g. `RackA-`), EPC memory size, and counter range
3. Enable **A/B paired tags** if each physical location needs two labels
4. Watch the live preview — it shows the generated TYP, HEX, and CRC-16 in real time
5. Click **🔍 Audit** to validate the full project before exporting
6. Click **📊 Excel** or **📄 CSV** to export the database

---

## Export Format

### Excel — Sheet 1 "RFID Tags"

| TYP             | TXPHEX                           | NAZOV          |
|:----------------|:---------------------------------|:---------------|
| SidPanMin000001A | 5369645061...                    | MINI SIDE PANEL |
| SidPanMin000001B | 5369645061...                    | MINI SIDE PANEL |

Each group is colour-coded. The TXPHEX column uses monospace font for readability.

### Excel — Sheet 2 "Summary"

One row per group with prefix, counter range, EPC size, tag count, and a SPOLU (total) formula.

### CSV

```
TYP,TXPHEX,NAZOV,EPC_BITS,GROUP
SidPanMin000001A,5369645061...,MINI SIDE PANEL,128,1
```

---

## Compatibility

| System | Format | Notes |
|:---|:---|:---|
| Loftware NiceLabel | .xlsx | Import via Database Wizard → Excel |
| Zebra ZebraDesigner | .csv | Import via Data Sources → CSV |
| SATO CODETHINQ | .csv | Import via Variable Data |
| Honeywell Easycoder | .csv | Import via Label Variables |
| Any WMS / ERP | .csv | Standard UTF-8, 5-column schema |

---

## Project File Format

Projects are saved as `.rfid` files — plain JSON arrays, version-controlled friendly:

```json
[
  {
    "nazov": "MINI SIDE PANEL",
    "prefix": "SidPanMin",
    "suffix": "",
    "counter_start": 1,
    "counter_end": 20,
    "epc_bits": 128,
    "ab_pair": true,
    "ab_grouped": true
  }
]
```

---

## Architecture

```
RFIDTagBuilder/
├── main.py        Entry point, logging setup
├── models.py      TagGroup dataclass, EPC constants, ascii_to_hex()
├── epc_logic.py   CRC-16, ASCII validation, duplicate detection, audit engine
├── export.py      Excel + CSV writers (batch mode, openpyxl)
├── app.py         CustomTkinter UI — GroupDialog, AuditDialog, App
├── build.bat      PyInstaller build script
└── requirements.txt
```

---

## Contributing

Issues and pull requests are welcome. Areas where contributions are especially valuable:

- GS1 SGTIN-96 / SGTIN-198 encoding support
- Import from existing CSV databases (reverse flow)
- Linux / macOS packaging
- Localisation (German, Polish, Dutch)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built for logistics engineers who need reliable RFID data — without the spreadsheet acrobatics.*
