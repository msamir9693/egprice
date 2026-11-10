"""Collect offers from all stores, match them to products, keep price history,
and compute best prices, today's biggest price gaps, and deals."""
import json
import logging
import statistics
import sys
from collections import Counter
from dataclasses import replace, asdict
from datetime import datetime, timezone
from pathlib import Path

import requests

from matching import match_reason, drop_outliers
from scrapers.base import StoreStats, fetch
from scrapers.registry import STORES

ROOT = Path(__file__).parent
PRODUCTS = ROOT / "products.json"
DATA = ROOT / "data"
HISTORY = DATA / "history.json"
OFFERS = DATA / "offers.json"
RUN_LOG = DATA / "run.log"

log = logging.getLogger("egprice")


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def load_products():
    return load_json(PRODUCTS, {"products": []})["products"]


def scrape(products, stores=STORES, fetcher=fetch):
    """Fetch every store's listing pages once. Returns (raw offers, {store name: StoreStats})."""
    raw, stats = [], {}
    for key, mod in stores.items():
        st = stats[mod.STORE] = StoreStats()
        if not getattr(mod, "ENABLED", True):
            st.notes.append("متوقف: " + getattr(mod, "DISABLED_REASON", ""))
            log.info("[%s] skipped (disabled: %s)", mod.STORE, getattr(mod, "DISABLED_REASON", ""))
            continue
        session = requests.Session()
        for url in mod.listing_urls(products):
            res = fetcher(url, session)
            st.requests += 1
            if res.status == "ok":
                st.ok += 1
                try:
                    found = mod.parse(res.text)
                except Exception as exc:  # a layout change must not stop the run
                    st.errors += 1
                    st.notes.append(f"parse error: {exc!r}")
                    log.exception("[%s] parse failed for %s", mod.STORE, url)
                    continue
                if not found:
                    st.notes.append(f"0 products on {url} (no results, or layout changed)")
                    log.warning("[%s] page fetched but 0 products parsed (no results, or layout changed): %s",
                                mod.STORE, url)
                st.raw_offers += len(found)
                raw.extend(found)
            elif res.status in ("blocked", "challenge"):
                st.blocked += 1
                st.notes.append(f"blocked ({res.detail}) - stopped for this run")
                log.warning("[%s] blocked (%s); not sending more requests this run", mod.STORE, res.detail)
                break
            else:
                st.errors += 1
                st.notes.append(f"{res.status} {res.code or ''} {url}".strip())
    return raw, stats


def match_offers(raw, products, stats=None):
    """Assign each raw offer to the product whose model code it carries. Returns offer dicts."""
    stats = stats if stats is not None else {}
    matched, rejected = [], Counter()
    seen = set()
    for o in raw:
        if (o.store, o.url) in seen:
            continue
        seen.add((o.store, o.url))
        for p in products:
            reason = match_reason(p, o)
            if not reason:
                matched.append(replace(o, product_id=p["id"]).to_dict())
                break
            if reason != "model":  # right model but rejected: worth logging
                rejected[reason] += 1
                log.info("[%s] rejected (%s) for %s: %s @ %s", o.store, reason, p["id"], o.title[:70], o.price)
                break

    kept = []
    by_product = {}
    for o in matched:
        by_product.setdefault(o["product_id"], []).append(o)
    for pid, items in by_product.items():
        best_per_store = {}
        for o in items:
            cur = best_per_store.get(o["store"])
            if cur is None or (o["in_stock"], -o["price"]) > (cur["in_stock"], -cur["price"]):
                best_per_store[o["store"]] = o
        good, dropped = drop_outliers(list(best_per_store.values()))
        for o in dropped:
            rejected["outlier"] += 1
            log.warning("[%s] outlier dropped for %s: %s @ %s", o["store"], pid, o["title"][:70], o["price"])
        kept.extend(good)
    for o in kept:
        if o["store"] in stats:
            stats[o["store"]].matched += 1
    return kept, rejected


def update_history(offers, history):
    """history[product_id][store] = list of {date, price}; one point per day per store."""
    today = datetime.now(timezone.utc).date().isoformat()
    for o in offers:
        if not o["in_stock"]:
            continue
        series = history.setdefault(o["product_id"], {}).setdefault(o["store"], [])
        lowest_today = min([o["price"]] + [p["price"] for p in series if p["date"] == today])
        series[:] = [p for p in series if p["date"] != today]
        series.append({"date": today, "price": lowest_today})
        series.sort(key=lambda p: p["date"])
        del series[:-120]  # keep ~4 months per store
    return history


def analyse(offers, history, products=None):
    """Build per-product comparison rows, today's biggest price gaps, and history-based deals."""
    by_product = {}
    for o in offers:
        by_product.setdefault(o["product_id"], []).append(o)

    products = products if products is not None else load_products()
    names = {p["id"]: p["name"] for p in products}
    comparisons, gaps, deals = [], [], []
    for pid, items in by_product.items():
        best_per_store = {}
        for o in items:
            cur = best_per_store.get(o["store"])
            if cur is None or o["price"] < cur["price"]:
                best_per_store[o["store"]] = o
        ranked = sorted(best_per_store.values(), key=lambda o: (not o["in_stock"], o["price"]))
        in_stock = [o for o in ranked if o["in_stock"]]
        best = in_stock[0] if in_stock else ranked[0]
        name = names.get(pid, pid)
        comparisons.append({"product_id": pid, "name": name, "best": best, "offers": ranked})

        if len(in_stock) >= 2:
            low, high = in_stock[0], in_stock[-1]
            diff = high["price"] - low["price"]
            if diff > 0:
                gaps.append({"product_id": pid, "name": name, "cheapest": low, "priciest": high,
                             "gap": diff, "gap_pct": round(diff / high["price"] * 100)})

        for o in in_stock:
            hist = [p["price"] for p in history.get(pid, {}).get(o["store"], [])]
            reasons = []
            if len(hist) >= 5 and o["price"] < min(hist[:-1]):
                reasons.append("أقل سعر مسجل")
            if len(hist) >= 5:
                median = statistics.median(hist)
                if median > 0 and o["price"] <= median * 0.85:
                    reasons.append(f"أقل من المعتاد بـ {round((1 - o['price'] / median) * 100)}%")
            if reasons:
                deals.append({**o, "name": name, "reasons": reasons})
    comparisons.sort(key=lambda c: c["name"])
    gaps.sort(key=lambda g: g["gap"], reverse=True)
    deals.sort(key=lambda d: d["price"])
    return comparisons, gaps, deals


def setup_logging():
    DATA.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    log.setLevel(logging.INFO)
    if not log.handlers:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        log.addHandler(console)
        file = logging.FileHandler(RUN_LOG, mode="w", encoding="utf-8")
        file.setFormatter(fmt)
        log.addHandler(file)


def print_summary(stats, rejected):
    log.info("---- summary per store ----")
    for name, st in stats.items():
        log.info("%-10s requests=%d ok=%d blocked=%d errors=%d listings=%d matched=%d %s",
                 name, st.requests, st.ok, st.blocked, st.errors, st.raw_offers, st.matched,
                 "; ".join(st.notes))
    if rejected:
        log.info("rejected after model match: %s", dict(rejected))


def run():
    setup_logging()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    products = load_products()
    raw, stats = scrape(products)
    offers, rejected = match_offers(raw, products, stats)
    history = update_history(offers, load_json(HISTORY, {}))
    comparisons, gaps, deals = analyse(offers, history, products)
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    OFFERS.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(),
        "category": load_json(PRODUCTS, {}).get("category", ""),
        "stores": {name: asdict(st) for name, st in stats.items()},
        "comparisons": comparisons, "gaps": gaps, "deals": deals,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(stats, rejected)
    found = {c["product_id"] for c in comparisons}
    missing = [p["id"] for p in products if p["id"] not in found]
    log.info("[done] %d offers, %d/%d products found, %d gaps, %d deals%s",
             len(offers), len(found), len(products), len(gaps), len(deals),
             f"; not found anywhere: {missing}" if missing else "")
    return comparisons, gaps, deals


if __name__ == "__main__":
    run()
