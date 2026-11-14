# Native Windows application

The Windows edition provides a Tkinter desktop window with five scenario
buttons and an embedded log console. It starts the Python authorizer in the
background and runs a client process for the selected MTI pair.

## Run from source

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_windows_gui.py
```

## Build locally

Requirements:

- Windows 10 or 11, 64-bit
- Python 3.12
- Visual Studio Build Tools with the C++ workload
- Inno Setup 6 for the installer

Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

The build performs three separate operations:

1. Cython compiles `iso8583_common.py` and `rules_engine.py` into native `.pyd`
   extension modules.
2. PyInstaller creates the GUI, client and server executable directories.
3. Inno Setup creates `dist\installer\ISO8583-Lab-Windows-Setup.exe`.

Cython is a compiler for Python extension modules; it is not by itself a full
standalone application packager. PyInstaller collects the Python runtime,
Tkinter and dependencies around the compiled modules.

## Build through GitHub Actions

Run the **Build Windows installer** workflow manually. Its downloadable
artifact contains `ISO8583-Lab-Windows-Setup.exe`.

## Installed layout

```text
ISO8583Lab\
├── iso8583-lab-gui.exe
├── client\iso8583-client.exe
├── server\iso8583-server.exe
├── specs\
├── rules\
├── client-rules\
├── messages\
└── docs\
```

The application binds the authorizer to `127.0.0.1:18583`; it does not expose
the service to the network. Closing the window terminates child processes.
