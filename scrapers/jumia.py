"""Jumia Egypt. DISABLED: on 2026-11-10 every request from a home connection got a
Cloudflare "Just a moment..." challenge (HTTP 403). We don't try to get around bot checks,
so this store stays off until there's an allowed way in (e.g. an affiliate/product feed).
The parser below matches Jumia's classic markup but has NOT been checked on a real page.
"""
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from .base import Offer, parse_price

STORE = "Jumia"
ENABLED = False
DISABLED_REASON = "Cloudflare challenge (403) on every request"
SEARCH = "https://www.jumia.com.eg/catalog/?q={q}"


def listing_urls(products):
    families = dict.fromkeys(p["family"] for p in products)
    return [SEARCH.format(q=quote_plus(f)) for f in families]


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    offers = []
    for art in soup.select("article.prd"):
        name_el = art.select_one("h3.name")
        price_el = art.select_one("div.prc")
        link_el = art.select_one("a.core")
        if not (name_el and price_el and link_el):
            continue
        price = parse_price(price_el.get_text())
        if price is None:
            continue
        url = "https://www.jumia.com.eg" + link_el.get("href", "")
        offers.append(Offer("", STORE, name_el.get_text(strip=True), price, url,
                            sku=art.get("data-sku", "") or link_el.get("data-id", "")))
    return offers
