# BufferWatch GUI – C2 Dashboard

Modern web-based Command & Control dashboard for the BufferWatch framework.

## Features
- **Real-time Console**: Full interactive shell with command history.
- **Visual Commands**: Quick buttons for common tasks (screenshot, keylogger, etc.).
- **Live Assets**: View screenshots and keylogs as they come in.
- **File Manager**: Browse and download files retrieved from victims.
- **Secure Uploads**: Upload files to the server and push them to victims.
- **Premium Dark UI**: Built with Bootstrap 5 and custom CSS for a state-of-the-art look.

## Requirements
Install dependencies using pip:
```bash
pip install -r requirements.txt
```

## Running the Dashboard
1. Open a terminal in the `gui` directory.
2. Run the application:
   ```bash
   python app.py
   ```
3. Open your browser and navigate to `http://127.0.0.1:5000`.

## Configuration
- **TCP Listener**: Listens on `0.0.0.0:50005`.
- **Web Server**: Runs on `0.0.0.0:5000`.
- **Payload**: Ensure your `backdoor3o.c` is configured with the correct IP address of this server.

## Project Structure
- `app.py`: Flask application and Socket.IO event handlers.
- `c2_handler.py`: TCP socket management and protocol implementation.
- `static/`: CSS, JS, and UI assets.
- `templates/`: HTML templates.
- `downloads/`: Files downloaded from victims.
- `screenshots/`: Captured screenshots.
- `keylogs/`: Saved keylogger files.
- `uploads/`: Files staged for uploading to victims.
