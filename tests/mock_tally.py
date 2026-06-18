"""A mock TallyPrime XML/HTTP gateway for tests.

Runs a real ``ThreadingHTTPServer`` on an ephemeral localhost port and answers
POSTed XML the way Tally would, so the genuine :class:`tally_mcp.client.TallyClient`
(httpx, retries, sanitization, error handling) can be exercised without a live
Tally. Routing is based on the request body; a small :class:`Controller` lets
tests inject delays (to trigger read-timeouts/retries) and toggle behaviours.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _fix(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# Object-collection type tag -> fixture file.
_COLLECTION_ROUTES = [
    ("<TYPE>Company</TYPE>", "companies.xml"),
    ("<TYPE>Group</TYPE>", "groups.xml"),
    ("<TYPE>StockItem</TYPE>", "stockitems.xml"),
    ("<TYPE>Bills</TYPE>", "bills.xml"),
    ("<TYPE>Voucher</TYPE>", "vouchers.xml"),
    ("<TYPE>Ledger</TYPE>", "ledgers.xml"),
]

# Report export ID -> fixture file.
_REPORT_ROUTES = [
    ("<ID>Profit and Loss</ID>", "pnl.xml"),
    ("<ID>Balance Sheet</ID>", "balance_sheet.xml"),
]


@dataclass
class Controller:
    """Shared mutable knobs that tests use to steer the mock."""

    request_count: int = 0
    delay_seconds: float = 0.0
    delay_remaining: int = 0  # apply the delay to this many upcoming requests
    last_body: str = ""

    def delay_next(self, count: int, seconds: float) -> None:
        self.delay_remaining = count
        self.delay_seconds = seconds


def route(body: str) -> bytes:
    """Map a request body to the bytes Tally would return."""
    # Deliberately malformed/dirty response for sanitization-over-the-wire tests.
    if "DIRTY" in body:
        # latin-1 encoded, with a raw control char and a non-ASCII byte.
        return ("<ENVELOPE><RESULT>caf\xe9\x04 ok</RESULT></ENVELOPE>").encode("latin-1")

    # An error path: Tally returns HTTP 200 with <LINEERROR>.
    if "Nonexistent Co" in body:
        return _fix("error_lineerror.xml")

    # Import (write) requests.
    if "<TALLYREQUEST>Import</TALLYREQUEST>" in body:
        return _fix("import_error.xml") if "FORCE_ERROR" in body else _fix("import_success.xml")

    # Report exports.
    for marker, fixture in _REPORT_ROUTES:
        if marker in body:
            return _fix(fixture)

    # Collection exports.
    for marker, fixture in _COLLECTION_ROUTES:
        if marker in body:
            return _fix(fixture)

    return b"<ENVELOPE></ENVELOPE>"


def _make_handler(controller: Controller):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence the default stderr logging
            pass

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            controller.request_count += 1
            controller.last_body = body

            if controller.delay_remaining > 0:
                controller.delay_remaining -= 1
                time.sleep(controller.delay_seconds)

            if "HTTP500" in body:
                self.send_response(500)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            payload = route(body)
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


@dataclass
class MockTally:
    """A running mock gateway. Use :func:`start` / context manager."""

    controller: Controller = field(default_factory=Controller)
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        assert self._server is not None
        return self._server.server_address[0]

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> "MockTally":
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.controller))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def __enter__(self) -> "MockTally":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
