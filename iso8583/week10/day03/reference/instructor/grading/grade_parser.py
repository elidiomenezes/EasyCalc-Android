#!/usr/bin/env python3
"""Compile and grade Week 10 / Day 3 parser without requiring Boost or CMake.

Usage:
    python3 grade_parser.py /path/to/cloned/student/repository

The five written answers are graded manually for another 25 points.
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
HIDDEN = HERE.parent / "tests" / "hidden_parser_tests.cpp"

# Each implementation category has its own marks. A failed component does not
# erase marks from otherwise working functions.
GROUPS = {
    "FIXED": (10, [
        "fixed_exact_end", "fixed_truncated", "fixed_past_end",
        "fixed_integer_overflow",
    ]),
    "LLVAR / LLLVAR": (15, [
        "llvar_zero_length", "llvar_bad_digit", "llvar_short_prefix",
        "llvar_above_spec_max", "llvar_truncated_data",
        "lllvar_max_length", "lllvar_bad_sign", "lllvar_short_data",
    ]),
    "Bitmaps": (15, [
        "bitmap_last_primary_bit", "bitmap_first_secondary_bit",
        "bitmap_missing_secondary", "bitmap_bad_hex",
        "bitmap_lowercase_hex",
    ]),
    "NIBSS table": (15, ["nibss_table_twenty_fields"]),
    "Complete message": (20, [
        "message_three_fields", "message_present_empty_field",
        "message_unsupported_field", "message_trailing_bytes",
        "message_invalid_mti", "message_secondary_de123",
    ]),
}

# A function that only throws ParseError must not receive credit for every
# malformed-message test. At least one successful parse is required before
# the negative cases in that category contribute to the grade.
BASELINES = {
    "FIXED": ["fixed_exact_end"],
    "LLVAR / LLLVAR": ["llvar_zero_length", "lllvar_max_length"],
    "Bitmaps": ["bitmap_last_primary_bit", "bitmap_first_secondary_bit",
                "bitmap_lowercase_hex"],
    "NIBSS table": ["nibss_table_twenty_fields"],
    "Complete message": ["message_three_fields", "message_present_empty_field",
                         "message_secondary_de123"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("student_root", type=Path)
    parser.add_argument("--compiler", default="g++")
    args = parser.parse_args()

    root = args.student_root.resolve()
    header = root / "include" / "iso8583_parser.hpp"
    implementation = root / "src" / "iso8583_parser.cpp"
    for required in (header, implementation, HIDDEN):
        if not required.is_file():
            parser.error(f"Missing required file: {required}")
    if shutil.which(args.compiler) is None:
        parser.error(f"Compiler not found: {args.compiler}")

    with tempfile.TemporaryDirectory(prefix="day03-parser-grade-") as staging:
        executable = Path(staging) / "parser_grade"
        build = [
            args.compiler, "-std=c++17", "-Wall", "-Wextra", "-Wpedantic",
            "-Wconversion", "-I", str(root / "include"),
            str(implementation), str(HIDDEN), "-o", str(executable),
        ]
        compiled = subprocess.run(build, text=True, capture_output=True,
                                  timeout=60, check=False)
        if compiled.returncode != 0:
            print("COMPILATION FAILED. Practical score: 0/75")
            print((compiled.stdout + compiled.stderr)[-6000:])
            return 1

        total = 0.0
        print("Week 10 / Day 3 - Automated Parser Grading")
        print("-" * 52)
        for group, (points, cases) in GROUPS.items():
            passed = 0
            outcomes = {}
            for name in cases:
                try:
                    result = subprocess.run(
                        [str(executable), name], text=True, capture_output=True,
                        timeout=5, check=False,
                    )
                    good = result.returncode == 0
                except subprocess.TimeoutExpired:
                    good = False
                outcomes[name] = good
                passed += int(good)
                print(f"  {'PASS' if good else 'FAIL'} {name}")
            valid_working_case = any(outcomes[name] for name in BASELINES[group])
            earned = points * passed / len(cases) if valid_working_case else 0.0
            total += earned
            if not valid_working_case:
                print("  No successful parse demonstrated; rejection-only "
                      "passes earn no marks.")
            print(f"{group}: {earned:.2f}/{points} ({passed}/{len(cases)} cases)\n")

        print(f"Practical score: {total:.2f}/75")
        print("Secure coding questions: 25 points (instructor grading)")
        print("Total course assignment: practical + written answers /100")
    return 0


if __name__ == "__main__":
    sys.exit(main())
