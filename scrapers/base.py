"""Shared helpers: polite HTTP fetch with logging, price parsing, and the Offer record."""
import logging
import random
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Optional
from urllib.parse import urlparse

import requests

log = logging.getLogger("egprice")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 30
DELAY_RANGE = (3.0, 6.0)  # seconds between two requests to the same host

# Text that means "you got a bot check, not the real page". We never try to solve these:
# the request is logged as blocked and the store is skipped for the rest of the run.
CHALLENGE_MARKERS = {
    "captcha": ("/errors/validatecaptcha", "captcha"),
    "akamai": ("bm-verify", "_sec/verify"),
    "cloudflare": ("just a moment...", "cf-chl", "challenge-platform"),
}


@dataclass
class Offer:
    product_id: str
    store: str
    title: str
    price: float  # EGP
    url: str
    in_stock: bool = True
    sku: str = ""  # store's own SKU / model code when it exposes one

    def to_dict(self):
        return asdict(self)


@dataclass
class FetchResult:
    url: str
    status: str  # ok | blocked | challenge | not_found | http_error | network_error
    code: Optional[int] = None
    text: Optional[str] = None
    detail: str = ""


@dataclass
class StoreStats:
    requests: int = 0
    ok: int = 0
    blocked: int = 0
    errors: int = 0
    raw_offers: int = 0
    matched: int = 0
    notes: list = field(default_factory=list)


_last_hit: dict = {}


def _wait_for(host: str):
    """Sleep so two requests to the same host are DELAY_RANGE seconds apart."""
    gap = random.uniform(*DELAY_RANGE)
    last = _last_hit.get(host)
    if last is not None:
        remaining = gap - (time.monotonic() - last)
        if remaining > 0:
            time.sleep(remaining)
    _last_hit[host] = time.monotonic()


def detect_challenge(text: str) -> Optional[str]:
    low = (text or "")[:20000].lower()
    for kind, markers in CHALLENGE_MARKERS.items():
        if any(m in low for m in markers):
            return kind
    return None


def fetch(url: str, session: Optional[requests.Session] = None) -> FetchResult:
    """Polite GET: waits between requests, classifies the answer and logs it.

    Retries once on network errors / 5xx only. Bot checks (403, captcha, challenge pages)
    are reported, not retried, so we don't keep hammering a site that said no.
    """
    host = urlparse(url).netloc
    http = session or requests
    for attempt in range(2):
        _wait_for(host)
        try:
            r = http.get(url, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as exc:
            res = FetchResult(url, "network_error", detail=type(exc).__name__)
            log.warning("[%s] network error (%s) %s", host, res.detail, url)
            if attempt == 0:
                continue
            return res
        code = r.status_code
        kind = detect_challenge(r.text)
        if code in (403, 429) or kind:
            res = FetchResult(url, "challenge" if kind else "blocked", code,
                              detail=kind or f"HTTP {code}")
            log.warning("[%s] BLOCKED %s (%s) %s", host, code, res.detail, url)
            return res
        if code == 404:
            log.warning("[%s] 404 not found %s", host, url)
            return FetchResult(url, "not_found", code)
        if code >= 500 and attempt == 0:
            log.warning("[%s] HTTP %s, retrying once %s", host, code, url)
            continue
        if code != 200 or not r.text:
            log.warning("[%s] HTTP %s %s", host, code, url)
            return FetchResult(url, "http_error", code)
        log.info("[%s] 200 %d bytes %s", host, len(r.text), url)
        return FetchResult(url, "ok", code, r.text)
    return FetchResult(url, "http_error")


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_PRICE_RE = re.compile(r"\d[\d,\.]*")


def parse_price(text: str) -> Optional[float]:
    """Turn strings like 'EGP 12,999.00', 'ج.م 1.299' or '٣٬٥٠٠' into a float."""
    if not text:
        return None
    text = text.translate(_ARABIC_DIGITS).replace("٬", ",").replace("٫", ".")
    m = _PRICE_RE.search(text)
    if not m:
        return None
    raw = m.group(0).rstrip(".,")
    # Egyptian sites use ',' as thousands separator; keep the last '.' as decimal if it has 1-2 digits after it.
    if "." in raw and "," in raw:
        raw = raw.replace(",", "")
    elif raw.count(".") == 1 and "," not in raw and len(raw.split(".")[1]) == 3:
        # '1.299' on Egyptian sites means 1299 (dot as thousands separator)
        raw = raw.replace(".", "")
    elif raw.count(",") > 0 and "." not in raw:
        raw = raw.replace(",", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None
