"""HTTP client for Tally's XML gateway."""

from __future__ import annotations

import time
from xml.etree import ElementTree as ET

import httpx

from .config import TallyConfig, config as default_config
from .xml_parser import TallyResponseError, parse, sanitize


class TallyConnectionError(RuntimeError):
    """Raised when Tally cannot be reached over the network."""


class TallyClient:
    """Thin wrapper around Tally's XML-over-HTTP endpoint.

    Posts an XML request body and returns either a parsed ``ElementTree`` root or
    the sanitized raw text.  Network errors are retried with a short backoff;
    Tally application errors (which arrive as HTTP 200) are surfaced immediately
    via :class:`~tally_mcp.xml_parser.TallyResponseError`.
    """

    def __init__(self, cfg: TallyConfig | None = None, *, retries: int = 2) -> None:
        self.cfg = cfg or default_config
        self.retries = retries

    def post(self, xml_body: str) -> str:
        """POST an XML request and return the sanitized response text."""
        headers = {"Content-Type": "text/xml; charset=utf-8"}
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(timeout=self.cfg.timeout) as http:
                    resp = http.post(
                        self.cfg.base_url,
                        content=xml_body.encode("utf-8"),
                        headers=headers,
                    )
                resp.raise_for_status()
                return sanitize(resp.content)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
            except httpx.HTTPError as exc:  # other HTTP-level errors: don't retry
                raise TallyConnectionError(
                    f"HTTP error talking to Tally at {self.cfg.base_url}: {exc}"
                ) from exc

        raise TallyConnectionError(
            f"Could not reach Tally at {self.cfg.base_url}. Is TallyPrime running with "
            f"the XML/HTTP gateway enabled (F1 > Settings > Connectivity > set as "
            f"Server, port {self.cfg.port})? Underlying error: {last_exc}"
        )

    def request(self, xml_body: str) -> ET.Element:
        """POST an XML request and return the parsed (and error-checked) root."""
        text = self.post(xml_body)
        return parse(text)

    def ping(self) -> bool:
        """Return True if Tally answers a minimal export request."""
        try:
            self.post("<ENVELOPE></ENVELOPE>")
            return True
        except (TallyConnectionError, TallyResponseError):
            return False
