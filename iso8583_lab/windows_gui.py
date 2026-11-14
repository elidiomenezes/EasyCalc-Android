#!/usr/bin/env python3
"""Native Windows launcher for the ISO 8583 classroom scenarios."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


APP_TITLE = "ISO 8583 Lab"
DEFAULT_PORT = 18583
SCENARIOS = (
    ("0100 / 0110", "Authorization", "authorization-approved.json"),
    ("0220 / 0230", "Financial advice", "financial-advice.json"),
    ("0420 / 0430", "Reversal advice", "reversal.json"),
    ("0600 / 0610", "Administrative", "administrative-request.json"),
    ("0800 / 0810", "Network sign-on", "network-sign-on.json"),
)
SPECS = (
    "nibss-v1.16.json",
    "ascii.json",
    "binary-bitmap.json",
    "ascii-bitmap-bcd-length.json",
    "binary-bitmap-bcd-length.json",
    "ascii-bitmap-binary-length.json",
    "ebcdic.json",
    "ebcdic-binary-bitmap.json",
    "packed-bcd-numeric.json",
)


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = application_dir()


class LabWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(900, 560)
        self.configure(bg="#111827")
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.server_process: subprocess.Popen[str] | None = None
        self.client_processes: set[subprocess.Popen[str]] = set()
        self.lines: queue.Queue[tuple[str, str]] = queue.Queue()
        self.spec_name = tk.StringVar(value=SPECS[0])
        self.port_text = tk.StringVar(value=str(DEFAULT_PORT))
        self.active_port: int | None = None
        self.status_text = tk.StringVar(value="Authorizer stopped")
        self.scenario_buttons: list[ttk.Button] = []

        self._configure_style()
        self._build_ui()
        self.after(60, self._drain_lines)
        self.after(150, self.start_server)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#111827")
        style.configure("Card.TFrame", background="#1F2937")
        style.configure(
            "TLabel", background="#111827", foreground="#E5E7EB", font=("Segoe UI", 10)
        )
        style.configure(
            "Title.TLabel", background="#111827", foreground="#F9FAFB",
            font=("Segoe UI Semibold", 19)
        )
        style.configure(
            "Status.TLabel", background="#1F2937", foreground="#93C5FD",
            font=("Segoe UI Semibold", 10)
        )
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(12, 9))
        style.configure("Scenario.TButton", font=("Consolas", 11, "bold"), padding=(10, 12))
        style.configure("TCombobox", padding=5)

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(18, 14))
        header.pack(fill="x")
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="Python client + authorizer • classroom transaction console",
        ).pack(side="left", padx=(18, 0), pady=(7, 0))

        controls = ttk.Frame(self, style="Card.TFrame", padding=12)
        controls.pack(fill="x", padx=18, pady=(0, 12))

        ttk.Label(controls, textvariable=self.status_text, style="Status.TLabel").pack(
            side="left", padx=(0, 18)
        )
        ttk.Label(controls, text="Specification:", background="#1F2937").pack(side="left")
        spec = ttk.Combobox(
            controls, textvariable=self.spec_name, values=SPECS, state="readonly", width=34
        )
        spec.pack(side="left", padx=(7, 14))
        spec.bind("<<ComboboxSelected>>", lambda _event: self.restart_server())

        ttk.Label(controls, text="Port:", background="#1F2937").pack(side="left")
        port = ttk.Entry(controls, textvariable=self.port_text, width=7)
        port.pack(side="left", padx=(7, 10))
        port.bind("<Return>", lambda _event: self.restart_server())

        ttk.Button(controls, text="Start authorizer", command=self.start_server).pack(
            side="left", padx=4
        )
        ttk.Button(
            controls, text="Stop", command=self.stop_server, width=5
        ).pack(side="left", padx=4)
        ttk.Button(controls, text="Clear console", command=self.clear_console).pack(
            side="right", padx=4
        )
        ttk.Button(
            controls, text="📁 Browse editable files", command=self.open_files_directory
        ).pack(side="right", padx=4)

        scenarios = ttk.Frame(self, padding=(18, 0, 18, 12))
        scenarios.pack(fill="x")
        for index, (pair, purpose, rules_file) in enumerate(SCENARIOS):
            button = ttk.Button(
                scenarios,
                text=f"{pair}\n{purpose}",
                style="Scenario.TButton",
                command=lambda file=rules_file, name=pair: self.run_scenario(file, name),
            )
            button.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0))
            scenarios.columnconfigure(index, weight=1)
            self.scenario_buttons.append(button)

        console_frame = ttk.Frame(self, padding=(18, 0, 18, 18))
        console_frame.pack(fill="both", expand=True)
        self.console = tk.Text(
            console_frame,
            background="#030712",
            foreground="#D1D5DB",
            insertbackground="#F9FAFB",
            selectbackground="#374151",
            relief="flat",
            padx=12,
            pady=10,
            wrap="none",
            font=("Cascadia Mono", 9),
            state="disabled",
        )
        vertical = ttk.Scrollbar(console_frame, orient="vertical", command=self.console.yview)
        horizontal = ttk.Scrollbar(console_frame, orient="horizontal", command=self.console.xview)
        self.console.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.console.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        console_frame.rowconfigure(0, weight=1)
        console_frame.columnconfigure(0, weight=1)
        self.console.tag_configure("server", foreground="#67E8F9")
        self.console.tag_configure("client", foreground="#86EFAC")
        self.console.tag_configure("system", foreground="#FDE68A")
        self.console.tag_configure("error", foreground="#FCA5A5")

    @staticmethod
    def _creation_flags() -> int:
        return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    @staticmethod
    def _environment() -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONUTF8"] = "1"
        return env

    def _program(self, role: str) -> list[str]:
        executable = BASE_DIR / role / f"iso8583-{role}.exe"
        if executable.exists():
            return [str(executable)]
        script = BASE_DIR / f"{role}.py"
        return [sys.executable, str(script)]

    def _spec_path(self) -> Path:
        return BASE_DIR / "specs" / self.spec_name.get()

    def _selected_port(self) -> int | None:
        try:
            port = int(self.port_text.get())
        except ValueError:
            port = 0
        if not 1 <= port <= 65535:
            messagebox.showerror(APP_TITLE, "Port must be a number from 1 to 65535.")
            return None
        return port

    def _spawn(self, command: list[str]) -> subprocess.Popen[str]:
        return subprocess.Popen(
            command,
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=self._environment(),
            creationflags=self._creation_flags(),
        )

    def _read_process(self, process: subprocess.Popen[str], tag: str) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.lines.put((tag, line))
        code = process.wait()
        if tag == "server":
            self.lines.put(("system" if code == 0 else "error", f"[SERVER EXIT {code}]\n"))
        else:
            self.lines.put(("system" if code == 0 else "error", f"[CLIENT EXIT {code}]\n"))
            self.client_processes.discard(process)

    def start_server(self) -> bool:
        if self.server_process and self.server_process.poll() is None:
            return True
        port = self._selected_port()
        if port is None:
            return False
        spec = self._spec_path()
        if not spec.exists():
            messagebox.showerror(APP_TITLE, f"Specification not found:\n{spec}")
            return False
        command = self._program("server") + [
            "--host", "127.0.0.1",
            "--port", str(port),
            "--spec", str(spec),
            "--rules", str(BASE_DIR / "rules" / "rules.json"),
            "--log-view", "both",
            "--color", "never",
        ]
        try:
            self.server_process = self._spawn(command)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Cannot start authorizer:\n{exc}")
            return False
        self.active_port = port
        self.status_text.set(f"Authorizer running • {self.spec_name.get()} • port {port}")
        self.lines.put(("system", f"\n[START AUTHORIZER] {' '.join(command)}\n"))
        threading.Thread(
            target=self._read_process, args=(self.server_process, "server"), daemon=True
        ).start()
        return True

    def stop_server(self) -> None:
        process = self.server_process
        if not process or process.poll() is not None:
            self.server_process = None
            self.active_port = None
            self.status_text.set("Authorizer stopped")
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        self.server_process = None
        self.active_port = None
        self.status_text.set("Authorizer stopped")

    def restart_server(self) -> None:
        self.stop_server()
        self.after(250, self.start_server)

    def run_scenario(self, rules_file: str, pair: str) -> None:
        port = self._selected_port()
        if port is None:
            return
        if self.server_process and self.server_process.poll() is None and self.active_port != port:
            self.stop_server()
        if not self.server_process or self.server_process.poll() is not None:
            if self.start_server():
                self.after(700, lambda: self.run_scenario(rules_file, pair))
            return
        command = self._program("client") + [
            "--host", "127.0.0.1",
            "--port", str(port),
            "--spec", str(self._spec_path()),
            "--rules", str(BASE_DIR / "client-rules" / rules_file),
            "--log-view", "both",
            "--color", "never",
        ]
        self.lines.put(("system", f"\n[RUN {pair}] {' '.join(command)}\n"))
        try:
            process = self._spawn(command)
        except OSError as exc:
            self.lines.put(("error", f"Cannot start client: {exc}\n"))
            return
        self.client_processes.add(process)
        threading.Thread(target=self._read_process, args=(process, "client"), daemon=True).start()

    def _drain_lines(self) -> None:
        if self.server_process and self.server_process.poll() is not None:
            self.server_process = None
            self.active_port = None
            self.status_text.set("Authorizer stopped")
        changed = False
        self.console.configure(state="normal")
        while True:
            try:
                tag, line = self.lines.get_nowait()
            except queue.Empty:
                break
            self.console.insert("end", line, tag)
            changed = True
        if changed:
            self.console.see("end")
        self.console.configure(state="disabled")
        self.after(60, self._drain_lines)

    def clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def open_files_directory(self) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(BASE_DIR))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(BASE_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(BASE_DIR)])
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Cannot open files directory:\n{exc}")

    def close(self) -> None:
        for process in tuple(self.client_processes):
            if process.poll() is None:
                process.terminate()
        self.stop_server()
        self.destroy()


def main() -> None:
    LabWindow().mainloop()


if __name__ == "__main__":
    main()
