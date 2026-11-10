"""Amazon.eg: one search per product family ("samsung u8000h"), 48 results per page.

Amazon's own title usually lacks the full model code, but the URL slug carries it
(".../Samsung-...-UA55U8000HUXEG/dp/..."), and matching looks at the URL too.
Amazon often answers automated requests with an Akamai bot check; fetch() reports that
as 'challenge' and the engine skips Amazon for the rest of the run.
"""
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from .base import Offer, parse_price

STORE = "Amazon.eg"
ENABLED = True
SEARCH = "https://www.amazon.eg/s?k={q}&language=en_AE"


def listing_urls(products):
    families = dict.fromkeys(p["family"] for p in products)
    return [SEARCH.format(q=quote_plus(f + " tv")) for f in families]


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    offers = []
    for card in soup.select('div[data-component-type="s-search-result"]'):
        link_el = card.select_one("a.a-link-normal.s-link-style[href], h2 a[href]") or \
            card.select_one("a.a-link-normal[href]")
        heads = [h.get_text(" ", strip=True) for h in card.select("h2")]
        price_el = card.select_one("span.a-price:not([data-a-strike]) > span.a-offscreen")
        if not (link_el and heads and price_el):
            continue
        price = parse_price(price_el.get_text())
        if price is None:
            continue
        href = link_el.get("href", "").split("?")[0].split("/ref=")[0]
        url = "https://www.amazon.eg" + href if href.startswith("/") else href
        offers.append(Offer("", STORE, " ".join(heads), price, url,
                            sku=card.get("data-asin", "")))
    return offers
