"""Parse and sanitize Tally XML responses.

Tally's XML output is notoriously not-quite-valid:

* It can contain raw control characters (e.g. ``&#4;``) that break standard XML
  parsers.
* It is frequently emitted in a Windows/latin-1 code page rather than UTF-8.
* It sometimes contains bare ``&`` characters that are not entity-escaped.
* Errors are returned with **HTTP 200** and surface as ``<LINEERROR>`` text
  rather than as an HTTP failure.

This module centralises that defensive handling so the rest of the code can work
with clean ``dict`` structures.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

# Valid XML 1.0 chars: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] |
# [#x10000-#x10FFFF]. Strip everything else (the stray control chars Tally emits).
_INVALID_XML_CHARS = re.compile(
    "[^\x09\x0a\x0d\x20-퟿-�\U00010000-\U0010FFFF]"
)

# A bare ampersand that is not the start of a valid entity (&amp; &#123; &#x1F;).
_BARE_AMPERSAND = re.compile(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]*;)")

# Numeric character references that point at characters XML 1.0 forbids
# (e.g. Tally's "&#4;"). ElementTree rejects these, so drop them.
_INVALID_CHARREF = re.compile(r"&#x?([0-9A-Fa-f]+);")


def _is_valid_xml_codepoint(cp: int) -> bool:
    return (
        cp in (0x9, 0xA, 0xD)
        or 0x20 <= cp <= 0xD7FF
        or 0xE000 <= cp <= 0xFFFD
        or 0x10000 <= cp <= 0x10FFFF
    )


def _strip_invalid_charrefs(text: str) -> str:
    def repl(match: "re.Match[str]") -> str:
        token = match.group(0)
        digits = match.group(1)
        base = 16 if token[2:3].lower() == "x" else 10
        try:
            cp = int(digits, base)
        except ValueError:
            return ""
        return token if _is_valid_xml_codepoint(cp) else ""

    return _INVALID_CHARREF.sub(repl, text)


class TallyResponseError(RuntimeError):
    """Raised when Tally returns an error payload (still HTTP 200)."""


def decode(raw: bytes | str) -> str:
    """Decode raw bytes from Tally, trying UTF-8 then falling back to latin-1."""
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def sanitize(raw: bytes | str) -> str:
    """Return a parseable XML string from Tally's loose output."""
    text = decode(raw)
    text = _INVALID_XML_CHARS.sub("", text)
    text = _strip_invalid_charrefs(text)
    text = _BARE_AMPERSAND.sub("&amp;", text)
    return text.strip()


def parse(raw: bytes | str) -> ET.Element:
    """Sanitize and parse a Tally response into an ElementTree root.

    Raises:
        TallyResponseError: if the payload is empty or reports a Tally error.
    """
    text = sanitize(raw)
    if not text:
        raise TallyResponseError("Empty response from Tally.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        snippet = text[:300]
        raise TallyResponseError(
            f"Could not parse Tally XML ({exc}). First 300 chars: {snippet!r}"
        ) from exc
    _raise_on_error(root, text)
    return root


def _raise_on_error(root: ET.Element, text: str) -> None:
    # <LINEERROR> appears inside error responses.
    line_error = root.find(".//LINEERROR")
    if line_error is not None and (line_error.text or "").strip():
        raise TallyResponseError(line_error.text.strip())

    # Import responses report failures via <RESPONSE><ERRORS> counters.
    errors = root.find(".//RESPONSE/ERRORS")
    if errors is not None and (errors.text or "0").strip() not in ("", "0"):
        # Surface the whole RESPONSE block for context.
        resp = root.find(".//RESPONSE")
        detail = ET.tostring(resp, encoding="unicode") if resp is not None else text[:300]
        raise TallyResponseError(f"Tally import reported errors: {detail}")


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    # Tally pads numbers/strings with surrounding whitespace and newlines.
    return value.strip()


def element_to_dict(elem: ET.Element) -> dict[str, Any]:
    """Shallow map of an element's direct children: ``{tag: text}``.

    The element's ``NAME`` attribute (common on Tally objects) is included as
    ``"NAME"`` when present. Repeated child tags are collapsed into a list.
    """
    result: dict[str, Any] = {}
    for child in elem:
        tag = child.tag
        text = _clean_text(child.text)
        if tag in result:
            existing = result[tag]
            if isinstance(existing, list):
                existing.append(text)
            else:
                result[tag] = [existing, text]
        else:
            result[tag] = text

    # Tally objects also expose NAME as an attribute. Child elements take
    # priority (they carry the fetched value); fall back to the attribute.
    name_attr = elem.get("NAME")
    if name_attr is not None and "NAME" not in result:
        result["NAME"] = _clean_text(name_attr)
    return result


def extract_objects(root: ET.Element, object_tag: str) -> list[dict[str, Any]]:
    """Extract all elements named ``object_tag`` as shallow dicts.

    Works for collection responses where each item is e.g. ``<LEDGER>``,
    ``<GROUP>``, ``<STOCKITEM>``, ``<COMPANY>`` or ``<VOUCHER>``.
    """
    return [element_to_dict(el) for el in root.iter(object_tag)]


def to_amount(value: str | None) -> float | None:
    """Parse a Tally amount string (e.g. ``"-15000.00"``) into a float.

    Returns ``None`` for blank values. Strips currency symbols, commas and
    surrounding whitespace; trailing ``Dr``/``Cr`` markers are honoured for sign
    (``Cr`` -> negative).
    """
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    sign = 1.0
    upper = s.upper()
    if upper.endswith("CR"):
        sign = -1.0
        s = s[:-2]
    elif upper.endswith("DR"):
        s = s[:-2]
    s = re.sub(r"[,\s₹]", "", s)
    try:
        return sign * float(s)
    except ValueError:
        return None
