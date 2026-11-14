#!/usr/bin/env python3
"""Generate the editable wire specifications used by the laboratory."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from iso8583.specs import default, default_ascii


def write_spec(path: Path, spec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(path)


def with_variable_lengths(base: dict, encoding: str) -> dict:
    """Change every variable-length prefix while preserving field data."""
    spec = deepcopy(base)
    for field in spec.values():
        original_width = field.get("len_type", 0)
        if not original_width:
            continue
        field["len_enc"] = encoding
        if encoding == "bcd":
            field["len_type"] = (original_width + 1) // 2
        elif encoding == "b":
            field["len_type"] = 1 if field["max_len"] <= 255 else 2
    return spec


def with_ebcdic_text(base: dict) -> dict:
    """Encode textual data and textual length prefixes using EBCDIC cp500."""
    spec = deepcopy(base)
    for field in spec.values():
        if field.get("data_enc") == "ascii":
            field["data_enc"] = "cp500"
        if field.get("len_enc") == "ascii":
            field["len_enc"] = "cp500"
    return spec


def packed_bcd_numeric() -> dict:
    """Build a hybrid profile with packed MTI and common numeric fields."""
    spec = deepcopy(default)
    spec["t"].update(data_enc="b", len_count="nibbles", max_len=4)
    numeric_fields = ("2", "3", "4", "7", "11", "12", "13", "39", "49", "90")
    for field_number in numeric_fields:
        field = spec[field_number]
        field["data_enc"] = "b"
        field["len_count"] = "nibbles"
        if field["max_len"] % 2:
            field["left_pad"] = "0"
        if field["len_type"]:
            field["len_enc"] = "bcd"
            field["len_type"] = (field["len_type"] + 1) // 2
    return spec


def nibss_v116() -> dict:
    """Build the NIBSS POS ISO 8583 v1.16 wire profile.

    NIBSS uses the ISO 8583:1987 field model with an ASCII MTI, ASCII-hex
    bitmaps, ASCII field data and ASCII variable-length prefixes.  The 2-byte
    binary TCP length prefix is transport framing and is therefore handled by
    the TCP adapter selected by the launcher, not by this pyiso8583 dictionary.
    """
    spec = deepcopy(default_ascii)
    spec["t"]["desc"] = "NIBSS Message Type Identifier"
    spec["p"]["desc"] = "NIBSS Primary Bitmap (ASCII hexadecimal)"
    spec["1"]["desc"] = "NIBSS Secondary Bitmap (ASCII hexadecimal)"

    overrides = {
        "3": (0, 6, "Processing Code (NIBSS alphanumeric)"),
        "55": (3, 510, "Integrated Circuit Card System Related Data"),
        "56": (3, 4, "Message Reason Code"),
        "59": (3, 255, "Transport Echo Data"),
        "60": (3, 999, "Payment Information"),
        "62": (3, 999, "Private Field, Management Data 1"),
        "63": (4, 9999, "Private Field, Management Data 2"),
        "64": (0, 64, "Primary Message Hash Value (SHA-256 hex)"),
        "123": (3, 15, "POS Data Code"),
        "124": (4, 9999, "Near Field Communication Data"),
        "128": (0, 64, "Secondary Message Hash Value (SHA-256 hex)"),
    }
    for field_number, (length_type, maximum, description) in overrides.items():
        spec[field_number].update(
            data_enc="ascii",
            len_enc="ascii",
            len_type=length_type,
            max_len=maximum,
            desc=description,
        )
    return spec


def main() -> None:
    output = Path(__file__).resolve().parent / "specs"
    write_spec(output / "nibss-v1.16.json", nibss_v116())
    write_spec(output / "ascii.json", default_ascii)
    write_spec(output / "binary-bitmap.json", default)
    write_spec(output / "ascii-bitmap-bcd-length.json", with_variable_lengths(default_ascii, "bcd"))
    write_spec(output / "binary-bitmap-bcd-length.json", with_variable_lengths(default, "bcd"))
    write_spec(output / "ascii-bitmap-binary-length.json", with_variable_lengths(default_ascii, "b"))
    write_spec(output / "ebcdic.json", with_ebcdic_text(default_ascii))
    write_spec(output / "ebcdic-binary-bitmap.json", with_ebcdic_text(default))
    write_spec(output / "packed-bcd-numeric.json", packed_bcd_numeric())


if __name__ == "__main__":
    main()
