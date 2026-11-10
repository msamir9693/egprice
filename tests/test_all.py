"""Offline tests: parsers on trimmed real pages (saved 2026-11-10), matching, bot-check
detection, engine flow with a fake fetcher, analysis, and site build."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers import amazon, twob, raya, btech, jumia, noon  # noqa: E402
from scrapers import base  # noqa: E402
from scrapers.base import parse_price, Offer, FetchResult, detect_challenge  # noqa: E402
import matching  # noqa: E402
import engine  # noqa: E402
import build_site  # noqa: E402

FX = ROOT / "tests" / "fixtures"

PRODUCTS = [
    {"id": "samsung-55-u8000h", "name": "Samsung 55 U8000H", "brand": "samsung",
     "family": "samsung u8000h", "model": "55U8000H", "min_price": 13000},
    {"id": "samsung-43-f6000f", "name": "Samsung 43 F6000F", "brand": "samsung",
     "family": "samsung f6000f", "model": "43F6000F", "min_price": 8000},
    {"id": "lg-65-nu830b", "name": "LG 65 NU830B", "brand": "lg",
     "family": "lg nu830b", "model": "65NU830B", "min_price": 17000},
]


def read(name):
    return (FX / name).read_text(encoding="utf-8")


def by_code(offers, code):
    return [o for o in offers if matching.normalize(code) in matching.normalize(o.title + o.url + o.sku)]


class PriceTests(unittest.TestCase):
    def test_prices(self):
        cases = {"EGP 12,999.00": 12999.0, "ج.م 1.299": 1299.0, "٣٬٥٠٠ ج.م": 3500.0,
                 "1,299.50": 1299.5, "EGP\xa020,660.00": 20660.0, "14,999\n EGP": 14999.0, "abc": None}
        for text, expected in cases.items():
            self.assertEqual(parse_price(text), expected, text)


class ParserTests(unittest.TestCase):
    """Fixtures are cut from real pages, so these tests break if we break the selectors."""

    def test_amazon(self):
        offers = amazon.parse(read("amazon.html"))
        self.assertGreaterEqual(len(offers), 3)
        tv = by_code(offers, "UA55U8000H")[0]
        self.assertEqual(tv.price, 20660.0)
        self.assertTrue(tv.url.startswith("https://www.amazon.eg/"))
        self.assertNotIn("/ref=", tv.url)
        self.assertTrue(tv.title.startswith("Samsung"))  # brand line + title line joined
        self.assertEqual(by_code(offers, "UA43F6000F")[0].price, 14399.0)

    def test_2b_uses_final_price_not_old_price(self):
        offers = twob.parse(read("2b.html"))
        tv = by_code(offers, "UA55U8000H")[0]
        self.assertEqual(tv.price, 22499.0)  # old price on the page is 31,599
        self.assertTrue(tv.url.startswith("https://2b.com.eg/en/"))

    def test_raya_grid_and_slider_cards(self):
        offers = raya.parse(read("raya.html"))
        self.assertEqual(by_code(offers, "65NU830B")[0].price, 28299.0)  # was 35,374
        self.assertEqual(by_code(offers, "UA55U8000H")[0].price, 20999.0)  # slider card
        self.assertTrue(all(o.url.startswith("https://www.rayashop.com/en/") for o in offers))

    def test_btech_flight_json(self):
        offers = btech.parse(read("btech.html"))
        self.assertEqual(len(offers), 3)
        tv = [o for o in offers if "55U8000H" in o.sku][0]
        self.assertEqual(tv.price, 22499.0)  # price before the checkout coupon
        self.assertIn("offering_id=", tv.url)
        self.assertTrue(tv.in_stock)

    def test_disabled_stores(self):
        self.assertFalse(jumia.ENABLED)
        self.assertFalse(noon.ENABLED)
        # their parsers still run on the old synthetic fixtures
        self.assertEqual(jumia.parse(read("jumia.html"))[0].price, 38999.0)
        self.assertEqual(len(noon.parse(read("noon.html"))), 2)

    def test_listing_urls(self):
        self.assertEqual(len(amazon.listing_urls(PRODUCTS)), 3)  # one per family
        urls = raya.listing_urls(PRODUCTS)
        self.assertIn("https://www.rayashop.com/en/tv-lg", urls)
        self.assertIn("https://www.rayashop.com/en/tv-samsung?page=2", urls)


class ChallengeTests(unittest.TestCase):
    def test_detects_real_bot_checks(self):
        self.assertEqual(detect_challenge(read("amazon_challenge.html")), "akamai")
        self.assertEqual(detect_challenge(read("jumia_challenge.html")), "cloudflare")
        self.assertIsNone(detect_challenge(read("2b.html")))
        self.assertIsNone(detect_challenge(read("raya.html")))

    def test_fetch_reports_challenge_without_retry(self):
        resp = mock.Mock(status_code=200, text=read("amazon_challenge.html"))
        session = mock.Mock()
        session.get.return_value = resp
        with mock.patch.object(base, "_wait_for"):
            res = base.fetch("https://www.amazon.eg/s?k=x", session)
        self.assertEqual(res.status, "challenge")
        self.assertEqual(session.get.call_count, 1)

    def test_fetch_waits_between_requests_to_same_host(self):
        base._last_hit.clear()
        sleeps = []
        with mock.patch.object(base.time, "sleep", sleeps.append), \
             mock.patch.object(base.random, "uniform", return_value=4.0):
            base._wait_for("x.com")
            base._wait_for("x.com")
            base._wait_for("y.com")
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], 3.5)


class MatchingTests(unittest.TestCase):
    P = PRODUCTS[0]

    def o(self, title, price=20000, url="https://x", sku=""):
        return Offer("", "S", title, price, url, sku=sku)

    def test_same_model_written_differently(self):
        for title in ["Samsung 55 Inch - UA55U8000H", "Samsung ua55u8000huxeg", "SAMSUNG UA-55U8000H",
                      "سامسونج ٥٥U8000H"]:
            self.assertEqual(matching.match_reason(self.P, self.o(title)), "", title)
        # model only in the URL (Amazon) or in the SKU (B.Tech)
        self.assertEqual(matching.match_reason(self.P, self.o("Samsung 55 Inch TV", url="https://a/UA55U8000HUXEG/dp/1")), "")
        self.assertEqual(matching.match_reason(self.P, self.o("Samsung 55 Inch TV", sku="1TSATVSM55U8000HL007")), "")

    def test_other_size_or_year_rejected(self):
        for title in ["Samsung UA50U8000H", "Samsung UA55DU8000", "Samsung UA55U8000F", "Samsung 155U8000H"]:
            self.assertEqual(matching.match_reason(self.P, self.o(title)), "model", title)

    def test_accessory_and_min_price(self):
        self.assertEqual(matching.match_reason(self.P, self.o("Remote for Samsung UA55U8000H", 350)), "accessory")
        self.assertEqual(matching.match_reason(self.P, self.o("Samsung UA55U8000H", 900)), "min_price")
        # real Amazon title seen 2026-11-10: a TV, not a remote
        self.assertEqual(matching.match_reason(
            self.P, self.o("Samsung UA55U8000H 55 inch Smart TV Without Magic Remote", 21000)), "")

    def test_outlier(self):
        offers = [{"price": p} for p in (20000, 21000, 22000, 9000)]
        kept, dropped = matching.drop_outliers(offers)
        self.assertEqual([o["price"] for o in dropped], [9000])
        self.assertEqual(len(kept), 3)


class EngineFlowTests(unittest.TestCase):
    def test_scrape_match_with_fake_fetcher(self):
        pages = {"amazon": read("amazon.html"), "2b.com.eg": read("2b.html"),
                 "rayashop": read("raya.html"), "btech": read("btech.html")}

        def fake_fetch(url, session=None):
            for key, html in pages.items():
                if key in url:
                    return FetchResult(url, "ok", 200, html)
            return FetchResult(url, "network_error")

        raw, stats = engine.scrape(PRODUCTS, fetcher=fake_fetch)
        offers, _ = engine.match_offers(raw, PRODUCTS, stats)
        stores_55 = {o["store"] for o in offers if o["product_id"] == "samsung-55-u8000h"}
        self.assertEqual(stores_55, {"Amazon.eg", "2B", "Raya", "B.Tech"})
        self.assertEqual(stats["Jumia"].requests, 0)  # disabled: no request sent
        # one offer per product per store
        keys = [(o["product_id"], o["store"]) for o in offers]
        self.assertEqual(len(keys), len(set(keys)))

    def test_store_stops_after_block(self):
        calls = []

        def blocked(url, session=None):
            calls.append(url)
            return FetchResult(url, "challenge", 200, detail="akamai")

        only_raya = {"raya": raya}
        _, stats = engine.scrape(PRODUCTS, stores=only_raya, fetcher=blocked)
        self.assertEqual(len(calls), 1)
        self.assertEqual(stats["Raya"].blocked, 1)


class AnalysisTests(unittest.TestCase):
    def offer(self, store, price, in_stock=True):
        return Offer("p1", store, "Samsung UA55U8000H", price, f"https://x/{store}", in_stock).to_dict()

    def test_best_price_gap_and_out_of_stock(self):
        offers = [self.offer("Raya", 21000), self.offer("2B", 22500), self.offer("B.Tech", 15000, in_stock=False)]
        comps, gaps, _ = engine.analyse(offers, {}, [{"id": "p1", "name": "TV"}])
        self.assertEqual(comps[0]["best"]["store"], "Raya")
        self.assertEqual(gaps[0]["gap"], 1500)
        self.assertEqual(gaps[0]["priciest"]["store"], "2B")

    def test_deal_on_new_low(self):
        hist = {"p1": {"Raya": [{"date": f"2026-10-{d:02d}", "price": 22000} for d in range(1, 6)]
                       + [{"date": "2026-11-10", "price": 20000}]}}
        _, _, deals = engine.analyse([self.offer("Raya", 20000)], hist, [])
        self.assertTrue(deals and "أقل سعر مسجل" in deals[0]["reasons"])

    def test_history_one_point_per_day_and_skips_out_of_stock(self):
        h = engine.update_history([self.offer("Raya", 22000)], {})
        h = engine.update_history([self.offer("Raya", 21000), self.offer("2B", 1, in_stock=False)], h)
        self.assertEqual(h["p1"]["Raya"][-1]["price"], 21000)
        self.assertEqual(len(h["p1"]["Raya"]), 1)
        self.assertNotIn("2B", h["p1"])


class SiteTests(unittest.TestCase):
    def test_site_renders_best_gap_and_arabic(self):
        out = ROOT / "docs" / "index.html"
        data = ROOT / "data" / "offers.json"
        backup_data = data.read_text(encoding="utf-8") if data.exists() else None
        backup_out = out.read_text(encoding="utf-8") if out.exists() else None
        try:
            offers = [Offer("p1", "Raya", "Samsung UA55U8000H", 20999, "https://r", True).to_dict(),
                      Offer("p1", "2B", "Samsung UA55U8000H", 22499, "https://b", True).to_dict()]
            comps, gaps, deals = engine.analyse(offers, {}, [{"id": "p1", "name": "Samsung 55 U8000H"}])
            data.parent.mkdir(exist_ok=True)
            data.write_text(json.dumps({"updated": "2026-11-10T06:00:00+00:00", "category": "شاشات",
                                        "stores": {"Raya": {"ok": 1, "matched": 1}, "Jumia": {}},
                                        "comparisons": comps, "gaps": gaps, "deals": deals},
                                       ensure_ascii=False), encoding="utf-8")
            build_site.build()
            page = out.read_text(encoding="utf-8")
            self.assertIn('lang="ar" dir="rtl"', page)
            self.assertIn("أفضل سعر عند <b><bdi>Raya</bdi></b>", page)
            self.assertIn("20,999 ج.م", page)
            self.assertIn("أرخص في <bdi>Raya</bdi> من <bdi>2B</bdi> بـ 1,500 ج.م", page)
            self.assertIn("<bdi>Jumia</bdi>: متوقف", page)
        finally:
            for path, backup in ((data, backup_data), (out, backup_out)):
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(backup, encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
