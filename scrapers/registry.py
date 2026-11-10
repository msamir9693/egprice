"""Register every store here.

A store module provides:
  STORE            display name
  ENABLED          False to skip it (set DISABLED_REASON too)
  listing_urls(products) -> list of pages to fetch for these products
  parse(html)      -> list of Offer (product_id left empty; matching fills it)
"""
from . import amazon, twob, raya, btech, jumia, noon

STORES = {
    "amazon": amazon,
    "2b": twob,
    "raya": raya,
    "btech": btech,
    "jumia": jumia,
    "noon": noon,
}
