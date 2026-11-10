"""B.Tech (btech.com): Next.js App Router site. The old Magento search URL is gone (404),
and the new search page loads results in the browser. The category page, however,
embeds its products as JSON inside `self.__next_f.push([1, "..."])` script chunks.

Only the first 20 products of a category are in the page (the best sellers), so a product
outside the top 20 won't be found here. The SKU contains the model code
("1TSATVSM55U8000HL007" -> 55U8000H), which matching uses.
"""
import json
import re
from .base import Offer

STORE = "B.Tech"
ENABLED = True
BASE = "https://btech.com"
CATEGORIES = ["/en/c/tvs-projectors/televisions"]

_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def listing_urls(products):
    return [BASE + c for c in CATEGORIES]


def _flight_text(html: str) -> str:
    out = []
    for chunk in _CHUNK.findall(html):
        try:
            out.append(json.loads('"' + chunk + '"'))
        except json.JSONDecodeError:
            continue
    return "".join(out)


def parse(html: str):
    text = _flight_text(html)
    dec = json.JSONDecoder()
    offers, seen = [], set()
    for m in re.finditer(r'\{"variant_id"', text):
        try:
            item, _ = dec.raw_decode(text, m.start())
        except json.JSONDecodeError:
            continue
        offer_id = item.get("offer_id")
        if not offer_id or offer_id in seen:
            continue
        seen.add(offer_id)
        price = item.get("price") or {}
        # final_price may include an item coupon applied at checkout; show the price before it
        value = price.get("final_without_coupon") or price.get("final_price")
        name = item.get("name")
        if not (value and name):
            continue
        url = f"{BASE}/en/p/{item.get('slug') or item.get('variant_id')}?offering_id={offer_id}"
        offers.append(Offer("", STORE, name, float(value), url,
                            in_stock=bool(item.get("is_in_stock", True)),
                            sku=item.get("sku", "")))
    return offers
