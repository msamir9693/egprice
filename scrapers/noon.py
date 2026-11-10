"""Noon Egypt. DISABLED: on 2026-11-10 requests from a home connection either timed out
or were dropped without an answer (bot protection), so we never saw a real page.
The __NEXT_DATA__ layout below is an UNVERIFIED guess; check it on a real page before
turning ENABLED on.
"""
import json
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from .base import Offer

STORE = "Noon"
ENABLED = False
DISABLED_REASON = "connection dropped / timed out (bot protection)"
SEARCH = "https://www.noon.com/egypt-en/search/?q={q}"


def listing_urls(products):
    families = dict.fromkeys(p["family"] for p in products)
    return [SEARCH.format(q=quote_plus(f)) for f in families]


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return []
    hits = (data.get("props", {}).get("pageProps", {})
                .get("catalog", {}).get("hits", []))
    offers = []
    for h in hits:
        price = h.get("sale_price") or h.get("price")
        title = h.get("name") or h.get("title")
        sku = h.get("sku") or h.get("id")
        if not (price and title and sku):
            continue
        url = f"https://www.noon.com/egypt-en/{h.get('url') or sku + '/p/'}"
        offers.append(Offer("", STORE, title, float(price), url,
                            in_stock=bool(h.get("is_buyable", True)), sku=str(sku)))
    return offers
