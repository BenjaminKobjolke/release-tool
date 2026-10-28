"""Integration tests for retrying FTP connection-limit refusals."""

import socketserver
import threading
from typing import cast
from unittest.mock import patch

import pytest

from release_tool.config import FTPConfig
from release_tool.exceptions import FTPError
from release_tool.ftp_client import FTPClient


class _FTPHandler(socketserver.StreamRequestHandler):
    """FTP server that refuses the first greeting, then accepts valid credentials."""

    def handle(self) -> None:
        server = cast(_FTPServer, self.server)
        server.connection_count += 1
        if server.first_refusal and server.connection_count == 1:
            self.wfile.write(b"421 Too many connections\r\n")
            return

        self.wfile.write(b"220 test FTP server\r\n")
        username = ""
        for raw_line in self.rfile:
            command, _, argument = raw_line.decode("ascii").rstrip("\r\n").partition(" ")
            command = command.upper()
            if command == "USER":
                username = argument
                self.wfile.write(b"331 password required\r\n")
            elif command == "PASS":
                response = (
                    b"230 logged in\r\n"
                    if username == "user" and argument == "good-password"
                    else b"530 Login incorrect.\r\n"
                )
                self.wfile.write(response)
            elif command == "CWD":
                response = (
                    b"250 directory changed\r\n"
                    if argument == "/ok"
                    else b"550 missing\r\n"
                )
                self.wfile.write(response)
            elif command == "PWD":
                self.wfile.write(b'257 "/ok"\r\n')
            elif command == "QUIT":
                self.wfile.write(b"221 goodbye\r\n")
                return
            else:
                self.wfile.write(b"502 unsupported command\r\n")


class _FTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False

    def __init__(self, *, first_refusal: bool = True) -> None:
        self.connection_count = 0
        self.first_refusal = first_refusal
        super().__init__(("127.0.0.1", 0), _FTPHandler)


def _client(port: int, password: str = "good-password") -> FTPClient:
    return FTPClient(
        FTPConfig(
            host="127.0.0.1",
            port=port,
            username="user",
            password=password,
            remote_path="/ok",
        )
    )


def test_connect_retries_after_limit_refusal_then_uses_free_slot() -> None:
    with _FTPServer() as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                patch("release_tool.ftp_client.time.sleep") as mock_sleep,
                _client(server.server_address[1]).connection(),
            ):
                pass

            assert server.connection_count == 2
            mock_sleep.assert_called_once_with(30)
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_connect_wrong_password_does_not_retry() -> None:
    with _FTPServer(first_refusal=False) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                patch("release_tool.ftp_client.time.sleep") as mock_sleep,
                pytest.raises(FTPError, match="Failed to connect.*530 Login incorrect"),
            ):
                _client(server.server_address[1], password="bad-password").connect()

            assert server.connection_count == 1
            mock_sleep.assert_not_called()
        finally:
            server.shutdown()
            thread.join(timeout=2)
