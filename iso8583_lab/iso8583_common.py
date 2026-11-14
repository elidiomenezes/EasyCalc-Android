"""Pure ISO 8583 parsing plus message-building and logging helpers."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

import iso8583


ROOT = Path(__file__).resolve().parent
DEFAULT_SPEC_PATH = ROOT / "specs" / "nibss-v1.16.json"
DEFAULT_RULES_PATH = ROOT / "rules" / "rules.json"
DATE_EXPRESSION = re.compile(r"^\$\(date\s+(.+?)\)$")
REGISTER_REFERENCE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def load_spec(path: str | Path) -> dict:
    spec_path = Path(path).expanduser()
    try:
        with spec_path.open("r", encoding="utf-8") as source:
            spec = json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load ISO 8583 spec {spec_path}: {exc}") from exc
    for required in ("t", "p", "1"):
        if required not in spec:
            raise ValueError(f"ISO 8583 spec {spec_path} is missing entry {required!r}")
    return spec


def load_message(
    path: str | Path,
    now: datetime | None = None,
    registers: dict[str, str] | None = None,
) -> dict[str, str]:
    message_path = Path(path).expanduser()
    try:
        with message_path.open("r", encoding="utf-8") as source:
            message = json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load message {message_path}: {exc}") from exc
    if not isinstance(message, dict) or not all(
        isinstance(field, str) and isinstance(value, str)
        for field, value in message.items()
    ):
        raise ValueError(f"message {message_path} must contain string fields and values")
    if "t" not in message:
        raise ValueError(f"message {message_path} is missing MTI field 't'")
    if "p" in message or "1" in message:
        raise ValueError("message must not define bitmaps p or 1; the encoder generates them")
    current = now or datetime.now()
    saved = registers or {}
    resolved = {}
    for field, value in message.items():
        expression = DATE_EXPRESSION.fullmatch(value)
        if expression:
            resolved[field] = current.strftime(expression.group(1))
            continue
        marker = "\x00DOLLAR\x00"
        text = value.replace("$$", marker)

        def replace_register(found: re.Match[str]) -> str:
            name = found.group(1)
            if name not in saved:
                raise ValueError(f"register ${name} is undefined in message {message_path}")
            return saved[name]

        resolved[field] = REGISTER_REFERENCE.sub(replace_register, text).replace(marker, "$")
    return resolved


def escape_raw(raw: bytes) -> str:
    """Render printable ASCII directly and every other byte as an escape."""
    rendered = []
    for byte in raw:
        if byte == 0x5C:
            rendered.append("\\\\")
        elif 0x20 <= byte <= 0x7E:
            rendered.append(chr(byte))
        else:
            rendered.append(f"\\x{byte:02X}")
    return "".join(rendered)


class MessageLogger:
    def __init__(
        self,
        *,
        view: str,
        spec_name: str,
        log_file: str | None,
        role: str,
        color: str,
    ) -> None:
        self.view = view
        self.spec_name = spec_name
        self.log_file = Path(log_file) if log_file else None
        self.role_color = {"server": "36", "client": "32"}.get(role)
        self.use_color = color == "always" or (color == "auto" and sys.stdout.isatty())
        self._lock = threading.Lock()

    def _emit(self, text: str, *, error: bool = False) -> None:
        with self._lock:
            color_code = "31" if error else self.role_color
            terminal_text = (
                f"\x1b[{color_code}m{text}\x1b[0m"
                if self.use_color and color_code
                else text
            )
            print(terminal_text, file=sys.stderr if error else sys.stdout)
            if self.log_file:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                with self.log_file.open("a", encoding="utf-8") as output:
                    output.write(text + "\n")

    def message(self, label: str, message: dict[str, str], raw: bytes) -> None:
        if self.view == "none":
            return
        lines = [f"\n[{datetime.now().isoformat(timespec='milliseconds')}] {label}"]
        if self.view in ("raw", "both"):
            lines.extend((
                f"spec        : {self.spec_name}",
                f"wire length : {len(raw)} bytes",
                f"raw         : {escape_raw(raw)}",
            ))
        if self.view in ("parsed", "both"):
            lines.append("parsed      :\n" + json.dumps(message, ensure_ascii=False, indent=2))
        self._emit("\n".join(lines))

    def status(self, text: str, *, error: bool = False) -> None:
        line = f"[{datetime.now().isoformat(timespec='milliseconds')}] {text}"
        self._emit(line, error=error)


def make_logger(args: argparse.Namespace, role: str) -> MessageLogger:
    return MessageLogger(
        view=args.log_view,
        spec_name=str(args.spec),
        log_file=args.log_file,
        role=role,
        color=args.color,
    )


def encode_message(message: dict[str, str], spec: dict) -> bytes:
    raw, _ = iso8583.encode(message, spec)
    return bytes(raw)


def decode_message(raw: bytes, spec: dict) -> dict[str, str]:
    decoded, _ = iso8583.decode(raw, spec)
    return decoded


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8583)
    parser.add_argument("--timeout", type=float, default=5.0)


def add_format_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec", default=str(DEFAULT_SPEC_PATH))
    parser.add_argument("--log-view", choices=("raw", "parsed", "both", "none"), default="both")
    parser.add_argument("--log-file", help="append logs to this file as well as stdout")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="color terminal logs by process role",
    )
