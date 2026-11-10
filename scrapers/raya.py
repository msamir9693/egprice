"""Raya Shop (rayashop.com): Nuxt site. Search results load in the browser only, but the
brand category pages (/en/tv-samsung, /en/tv-lg) are server-rendered with 20 products per
page, so we read those. Titles end with the model code ("... - UA55U8000H").

Two card types exist on the page: the main grid (article.ProductCardPlpGrid) and a
"best sellers" slider (a.HorizontalProductCard); both are read.
"""
from bs4 import BeautifulSoup
from .base import Offer, parse_price

STORE = "Raya"
ENABLED = True
BASE = "https://www.rayashop.com"
CATEGORY = {"samsung": "/en/tv-samsung", "lg": "/en/tv-lg"}
PAGES = {"samsung": 3, "lg": 2}  # LG had only 2 pages on 2026-11-10


def listing_urls(products):
    urls = []
    for brand in dict.fromkeys(p["brand"] for p in products):
        path = CATEGORY.get(brand)
        if path:
            pages = PAGES.get(brand, 2)
            urls += [BASE + path] + [f"{BASE}{path}?page={n}" for n in range(2, pages + 1)]
    return urls


def _abs(href):
    return BASE + href if href.startswith("/") else href


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    offers = []
    for card in soup.select("article.ProductCardPlpGrid"):
        name = card.select_one(".ProductCardPlpGrid__Name")
        link = card.select_one("a[href]")
        price = card.select_one(".ProductCardPlpGrid__Price .currency")
        if not (name and link and price):
            continue
        value = parse_price(price.get_text())
        if value is None:
            continue
        text = card.get_text(" ", strip=True).lower()
        in_stock = "out of stock" not in text and "notify me" not in text
        offers.append(Offer("", STORE, name.get_text(" ", strip=True), value,
                            _abs(link["href"]), in_stock))
    for card in soup.select("a.HorizontalProductCard[href]"):
        name = card.select_one(".HorizontalProductCard__Title")
        price = card.select_one(".HorizontalProductCard__Pricing .currency") or \
            card.select_one(".currency")
        if not (name and price):
            continue
        value = parse_price(price.get_text())
        if value is None:
            continue
        offers.append(Offer("", STORE, name.get_text(" ", strip=True), value,
                            _abs(card["href"])))
    return offers
