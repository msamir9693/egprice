"""2B (2b.com.eg): Magento store, search results are server-rendered.

Titles end with the model code ("... - UA55U8000H"); the real price is the
data-price-amount of the element marked data-price-type="finalPrice".
Search matches whole words only ("NU830B" finds nothing, "55NU830B6LA" does), so we search
per brand ("samsung tv", 36 results) and let matching pick the models.
"""
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from .base import Offer, parse_price

STORE = "2B"
ENABLED = True
SEARCH = "https://2b.com.eg/en/catalogsearch/result/?q={q}&product_list_limit=36"


def listing_urls(products):
    brands = dict.fromkeys(p["brand"] for p in products)
    return [SEARCH.format(q=quote_plus(b + " tv")) for b in brands]


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    offers, seen = [], set()
    for item in soup.select("li.product-item"):
        link = item.select_one("a.product-item-link")
        price_el = item.select_one('[data-price-type="finalPrice"]')
        if not (link and price_el):
            continue
        url = link.get("href", "")
        if url in seen:
            continue
        seen.add(url)
        price = parse_price(price_el.get("data-price-amount") or price_el.get_text())
        if price is None:
            continue
        in_stock = not item.select_one(".stock.unavailable, .out-of-stock")
        offers.append(Offer("", STORE, link.get_text(" ", strip=True), price, url, in_stock))
    return offers
