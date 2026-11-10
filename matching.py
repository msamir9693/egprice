"""Decide whether a store listing is the same product as one in products.json.

Rule: the product's model code (e.g. "55U8000H", "50NU830B") must appear in the listing's
title, URL or SKU after normalising (upper case, Latin digits, no spaces/dashes). This makes
"UA55U8000HUXEG", "ua55u8000h" and B.Tech's SKU "1TSATVSM55U8000HL007" all match "55U8000H",
while "UA55DU8000" (an older model) and "UA50U8000H" (another size) don't.

On top of that: accessory words are rejected, prices below the product's min_price are
rejected, and offers far below the other stores' median are dropped as outliers.
"""
import re
import statistics

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Listings that mention the model but aren't the TV itself.
# Phrases, not single words: a real TV can say "Without Magic Remote" or "with stand".
ACCESSORY_WORDS = (
    "remote for", "remote control for", "replacement remote", "wall mount", "wallmount",
    "bracket", "stand for", "screen protector", "cover for", "compatible with", "replacement",
    "spare part", "backlight", "power board",
    "ريموت لشاشة", "ريموت كنترول لشاشة", "حامل شاشة", "حامل حائط", "قطع غيار", "متوافق مع",
)

OUTLIER_RATIO = 0.6  # drop offers cheaper than 60% of the other stores' median


def normalize(text: str) -> str:
    text = (text or "").translate(_ARABIC_DIGITS).upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def _code_pattern(code: str):
    # the code must not be glued to a digit before it ("155U8000H" is not "55U8000H")
    return re.compile(r"(?<![0-9])" + re.escape(normalize(code)))


def is_accessory(title: str) -> bool:
    low = (title or "").lower()
    return any(w in low for w in ACCESSORY_WORDS)


def match_reason(product: dict, offer) -> str:
    """Return '' when the offer is this product, otherwise a short rejection reason."""
    hay = normalize(" ".join([offer.title, offer.url, offer.sku]))
    codes = [product["model"]] + product.get("aliases", [])
    if not any(_code_pattern(c).search(hay) for c in codes):
        return "model"
    if is_accessory(offer.title):
        return "accessory"
    if offer.price < product.get("min_price", 0):
        return "min_price"
    return ""


def drop_outliers(offers: list) -> tuple:
    """offers: dicts of ONE product. Returns (kept, dropped)."""
    if len(offers) < 3:
        return offers, []
    kept, dropped = [], []
    for o in offers:
        others = [x["price"] for x in offers if x is not o]
        if o["price"] < statistics.median(others) * OUTLIER_RATIO:
            dropped.append(o)
        else:
            kept.append(o)
    return kept, dropped
