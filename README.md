# MemoryRift

> **For educational and authorized penetration testing use only.**
> Running this software against systems you do not own or have explicit written permission to test is illegal.

A full-stack Command & Control (C2) framework built as a Final Year Project — Windows reverse-shell implant, real-time keylogger, and a synthwave-themed web dashboard with a built-in payload compiler.

---

## Screenshots

![MemoryRift Dashboard](.github/assets/Screenshot%202026-06-13%20152733.png)
*Synthwave C2 dashboard — console, live screenshot viewer, keystream panel, Payload Forge, File Inject, and Vault.*

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Attacker Machine (Linux)                            │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │  MemoryRift Web Dashboard  :5000             │    │
│  │  Flask + Flask-SocketIO + eventlet           │    │
│  │                                              │    │
│  │  ┌────────────┐   ┌──────────────────────┐  │    │
│  │  │  Browser   │   │  TCP Listener :50005  │  │    │
│  │  │  (UI/WS)   │   │  c2_handler.py        │  │    │
│  │  └────────────┘   └──────────────────────┘  │    │
│  └─────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
                          ▲ reverse TCP
                          │
┌─────────────────────────────────────────────────────┐
│  Victim Machine (Windows)                            │
│  backdoor3o.exe                                      │
│  – XOR-obfuscated strings (key 0xAA)                 │
│  – Registry + Scheduled Task persistence             │
│  – GDI screenshot capture                            │
│  – Win32 keylogger (GetKeyState polling)             │
└─────────────────────────────────────────────────────┘
```

---

## Features

### Web Dashboard (Synthwave UI)
- **Real-time console** — send commands, view output live via Socket.IO
- **Live screenshot viewer** — renders GDI captures from the victim instantly
- **Keystream panel** — live keylog feed streamed from the victim
- **Payload Forge** — compile a custom `backdoor.exe` with your C2 IP/port directly from the browser (mingw-w64 cross-compilation)
- **File Inject** — upload files to the server for later push to the victim
- **Vault** — browse exfiltrated files, saved keylogs, and built payloads
- **Activity ticker** — live horizontal event strip at the bottom of the dashboard
- **Synthwave aesthetic** — matrix rain, neon glow panels, perspective floor grid, connection flash animation

### Implant (`backdoor3o.c`)
| Command | Description |
|---|---|
| `screenshot` | Captures desktop via GDI, sends raw BMP |
| `keylog_start` | Starts Win32 keylogger thread (live stream) |
| `persist` | Installs Registry Run key + Scheduled Task |
| `download <path>` | Exfiltrates a file from the victim |
| `upload <file>` | Pushes a file from server to victim |
| `vuln <arg>` | Demonstrates controlled stack overflow |
| `cd <dir>` | Changes working directory |
| `cat <file>` | Reads and sends a file's contents |
| `<any>` | Executed as shell command via `cmd.exe /c` |

### Keylogger (`keylogger.h`)
- Header-only, spawns a separate Win32 thread
- Polls `GetKeyState()` every 10 ms, maps virtual keys to printable characters
- Streams `[KEYLOG] <char>\n` lines over the C2 socket live
- Also writes to `%APPDATA%\windows_log.txt` locally on the victim

---

## Project Structure

```
MemoryRift/
├── backdoor3o.c          # Windows implant source (C, Win32 API)
├── keylogger.h           # Header-only keylogger thread
├── server.py             # Standalone CLI C2 listener (alternative to GUI)
├── gui/
│   ├── app.py            # Flask app — routes + SocketIO events + build API
│   ├── c2_handler.py     # TCP backend — recv_line_filtered, idle keylog reader
│   ├── requirements.txt
│   ├── templates/
│   │   └── index.html    # Synthwave dashboard
│   └── static/
│       ├── css/style.css # Synthwave theme — pink/cyan/green neon palette
│       └── js/main.js    # Socket.IO client + matrix rain + visual effects
└── README.md
```

---

## Setup

### Prerequisites

```bash
# Python dependencies
pip install flask flask-socketio eventlet colorama

# Cross-compiler for payload building (Linux)
sudo apt install mingw-w64
```

### Run the Dashboard

```bash
cd gui/
python3 app.py
```

Open `http://<your-ip>:5000` in a browser.
The C2 listener starts automatically on port `50005`.

### Build a Payload (from the GUI)

1. Open the **Payload Forge** panel
2. Enter your attacker IP and port
3. Choose architecture (x64 / x86)
4. Click **FORGE PAYLOAD** — mingw-w64 compiles a custom `.exe` in-browser
5. Download directly from the dashboard

### Build Manually

```bash
# x64
x86_64-w64-mingw32-gcc backdoor3o.c -o payload.exe \
    -lws2_32 -lgdi32 -luser32 -lshlwapi -mwindows -O2 -s

# x86
i686-w64-mingw32-gcc backdoor3o.c -o payload.exe \
    -lws2_32 -lgdi32 -luser32 -lshlwapi -mwindows -O2 -s
```

---

## Technical Details

### Protocol Synchronization
The server uses `recv_line_filtered()` in `c2_handler.py` which transparently routes `[KEYLOG]` prefixed lines to the browser via SocketIO without surfacing them to command handlers — preventing interleaving between live keylog stream and command responses.

### String Obfuscation
The C2 IP is XOR-encoded in the implant binary with key `0xAA` and decoded at runtime, making static string extraction harder:
```c
void xor_decode(char *buf, const char *enc, int len) {
    for (int i = 0; i < len; i++) buf[i] = enc[i] ^ 0xAA;
}
```

### Persistence Mechanisms
Two independent persistence methods are installed simultaneously:
1. **Registry Run key** — `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\OneDriveStandaloneUpdateHelper`
2. **Scheduled Task** — `OneDriveStandaloneUpdateTask` (runs at logon)

Both point to the implant copied to `%APPDATA%\OneDriveStandaloneUpdate.exe`.

---

## Stack

| Layer | Technology |
|---|---|
| Implant | C (Win32 API, Winsock2, GDI+) |
| Server | Python 3, Flask, Flask-SocketIO, eventlet |
| Frontend | HTML5, CSS3 (custom synthwave theme), JavaScript (ES2022) |
| Real-time | Socket.IO 4.x |
| Cross-compilation | mingw-w64 |

---

## Disclaimer

This project was developed solely for educational purposes. It demonstrates C2 architecture, Windows persistence techniques, and real-time web dashboards. **Do not deploy against any system without explicit written authorization from the owner.** The authors accept no liability for misuse.
