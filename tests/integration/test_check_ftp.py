"""Integration tests for the read-only FTP profile check command."""

import logging
import socketserver
import threading
from pathlib import Path

from release_tool.cli import main


class _FTPHandler(socketserver.StreamRequestHandler):
    """Small FTP server for login and CWD checks, with no write commands."""

    def handle(self) -> None:
        self.wfile.write(b"220 test FTP server\r\n")
        username = ""
        for raw_line in self.rfile:
            command, _, argument = raw_line.decode("ascii").rstrip("\r\n").partition(" ")
            command = command.upper()
            if command == "USER":
                username = argument
                self.wfile.write(b"331 password required\r\n")
            elif command == "PASS":
                if username == "user" and argument == "good-password":
                    self.wfile.write(b"230 logged in\r\n")
                else:
                    self.wfile.write(b"530 login rejected\r\n")
            elif command == "CWD":
                response = (
                    b"250 directory changed\r\n"
                    if argument == "/ok"
                    else b"550 no such directory\r\n"
                )
                self.wfile.write(response)
            elif command == "QUIT":
                self.wfile.write(b"221 goodbye\r\n")
                return
            else:
                self.wfile.write(b"502 unsupported command\r\n")


class _FTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


def _profiles(port: int, *, only_good: bool = False) -> str:
    sections = [
        f"[good]\nhost = 127.0.0.1\nport = {port}\nusername = user\npassword = good-password\nremote_path = /ok\n"
    ]
    if not only_good:
        sections.extend(
            [
                f"[wrong-password]\nhost = 127.0.0.1\nport = {port}\nusername = user\npassword = bad-password\nremote_path = /ok\n",
                f"[missing-folder]\nhost = 127.0.0.1\nport = {port}\nusername = user\npassword = good-password\nremote_path = /missing\n",
            ]
        )
    return "\n".join(sections)


def test_check_ftp_against_local_server(tmp_path: Path, caplog) -> None:
    with _FTPServer(("127.0.0.1", 0), _FTPHandler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        profiles = tmp_path / "profiles.ini"
        profiles.write_text(_profiles(port), encoding="utf-8")

        caplog.set_level(logging.INFO)
        try:
            result = main(["check-ftp", "--profiles", str(profiles), "--timeout", "5"])

            assert result == 1
            output = caplog.text
            assert "OK   good:" in output
            assert "FAIL wrong-password:" in output
            assert "FAIL missing-folder:" in output
            assert "bad-password" not in output

            profiles.write_text(_profiles(port, only_good=True), encoding="utf-8")
            assert main(["check-ftp", "--profiles", str(profiles), "--timeout", "5"]) == 0
        finally:
            server.shutdown()
            thread.join(timeout=2)
