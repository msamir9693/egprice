"""Render data/offers.json into docs/index.html (static, no backend needed)."""
import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "offers.json"
OUT = ROOT / "docs" / "index.html"


def egp(v):
    return f"{v:,.0f} ج.م"


def esc(s):
    return html.escape(str(s), quote=True)


def bdi(s):
    """Latin store names like '2B' inside Arabic sentences need their own text direction."""
    return f"<bdi>{esc(s)}</bdi>"


def render_comparison(c):
    best = c["best"]
    rows = []
    for o in c["offers"]:
        is_best = o is best or (o["store"] == best["store"] and o["price"] == best["price"])
        cls = " class='best'" if is_best else ""
        stock = "متوفر" if o["in_stock"] else "غير متوفر"
        badge = " <span class='tag'>الأفضل</span>" if is_best else ""
        rows.append(
            f"<tr{cls}><td>{esc(o['store'])}{badge}</td>"
            f"<td class='price'>{egp(o['price'])}</td>"
            f"<td>{stock}</td>"
            f"<td><a href='{esc(o['url'])}' target='_blank' rel='nofollow sponsored noopener'>افتح</a></td></tr>"
        )
    return f"""
<section class='card'>
  <h2>{esc(c['name'])}</h2>
  <p class='summary'>أفضل سعر عند <b>{bdi(best['store'])}</b>: <span class='price'>{egp(best['price'])}</span></p>
  <div class='table-wrap'><table>
    <thead><tr><th>المتجر</th><th>السعر</th><th>الحالة</th><th></th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>
</section>"""


def render_gaps(gaps):
    if not gaps:
        return "<p class='empty'>محتاجين المنتج يبقى متوفر في محلّين على الأقل عشان نقارن.</p>"
    items = []
    for g in gaps[:10]:
        low, high = g["cheapest"], g["priciest"]
        items.append(
            f"<li class='deal'><div><b>{esc(g['name'])}</b><br>"
            f"<small>أرخص في {bdi(low['store'])} من {bdi(high['store'])} بـ {egp(g['gap'])} ({g['gap_pct']}%)</small></div>"
            f"<div class='price'>{egp(low['price'])}</div>"
            f"<a class='btn' href='{esc(low['url'])}' target='_blank' rel='nofollow sponsored noopener'>افتح</a></li>"
        )
    return f"<ul class='deals'>{''.join(items)}</ul>"


def render_stores(stores):
    if not stores:
        return ""
    parts = []
    for name, st in stores.items():
        if st.get("ok"):
            state = f"اتحدث ({st.get('matched', 0)} عرض)"
        elif st.get("blocked"):
            state = "محجوب المرة دي"
        elif st.get("requests"):
            state = "فشل التحديث"
        else:
            state = "متوقف"
        parts.append(f"{bdi(name)}: {state}")
    return "<p class='note'>المحلات: " + " · ".join(parts) + "</p>"


def render_deals(deals):
    if not deals:
        return "<p class='empty'>مفيش عروض مميزة دلوقتي. هنرجع نشيّك تاني في التحديث الجاي.</p>"
    items = []
    for d in deals[:30]:
        items.append(
            f"<li class='deal'><div><b>{esc(d['name'])}</b><br>"
            f"<small>{esc(d['store'])} · {' · '.join(esc(r) for r in d['reasons'])}</small></div>"
            f"<div class='price'>{egp(d['price'])}</div>"
            f"<a class='btn' href='{esc(d['url'])}' target='_blank' rel='nofollow sponsored noopener'>اشتري</a></li>"
        )
    return f"<ul class='deals'>{''.join(items)}</ul>"


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2330;--muted:#6b7280;--accent:#0f766e;--best:#ecfdf5;--line:#e5e7eb}
@media (prefers-color-scheme: dark){:root{--bg:#0f1115;--card:#171a21;--text:#e6e8ec;--muted:#9aa3b2;--accent:#2dd4bf;--best:#0f2a26;--line:#2a2f3a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif;line-height:1.6}
header{padding:24px 16px 8px;max-width:960px;margin:auto}
h1{margin:0 0 4px;font-size:26px}
.sub{color:var(--muted);margin:0;font-size:14px}
main{max-width:960px;margin:auto;padding:8px 16px 48px}
h2{font-size:19px;margin:0 0 8px}
h3{font-size:18px;margin:24px 0 12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:14px}
.summary{margin:0 0 10px}
.price{font-weight:700;color:var(--accent);white-space:nowrap}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{padding:8px;border-bottom:1px solid var(--line);text-align:right}
th{color:var(--muted);font-weight:600;font-size:13px}
tr.best{background:var(--best)}
.tag{background:var(--accent);color:#fff;border-radius:6px;padding:1px 6px;font-size:12px;margin-right:4px}
a{color:var(--accent)}
.deals{list-style:none;padding:0;margin:0}
.deal{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-bottom:10px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.deal>div:first-child{flex:1;min-width:160px}
.btn{background:var(--accent);color:#fff;text-decoration:none;padding:8px 14px;border-radius:10px;font-weight:600}
.empty,.note{color:var(--muted)}
.note{font-size:13px;margin-top:24px}
@media (max-width:480px){h1{font-size:22px}th,td{padding:6px 4px;font-size:14px}}
"""


def build():
    data = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {
        "updated": None, "comparisons": [], "deals": []}
    updated = data.get("updated")
    stamp = datetime.fromisoformat(updated).strftime("%Y-%m-%d %H:%M UTC") if updated else "لسه ما اتحدثش"
    category = data.get("category", "")
    comps = data.get("comparisons", [])
    comp_html = "".join(render_comparison(c) for c in comps) or \
        "<p class='empty'>مفيش منتجات متسجلة لسه.</p>"
    page = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>مقارنة الأسعار في مصر</title>
<meta name="description" content="قارن أسعار {esc(category or 'المنتجات')} بين المحلات المصرية وشوف أرخص سعر.">
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>مقارنة الأسعار في مصر{(' — ' + esc(category)) if category else ''}</h1>
  <p class="sub">آخر تحديث: {stamp}</p>
</header>
<main>
  <h3>أكبر فروق الأسعار النهارده</h3>
  {render_gaps(data.get('gaps', []))}
  <h3>أفضل العروض</h3>
  {render_deals(data.get('deals', []))}
  <h3>مقارنة الأسعار</h3>
  {comp_html}
  {render_stores(data.get('stores', {}))}
  <p class="note">الأسعار بتتجمع تلقائياً من المواقع وممكن تختلف عن السعر الفعلي. اتأكد من السعر في الموقع قبل الشراء.</p>
</main>
</body>
</html>
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"[site] wrote {OUT}")


if __name__ == "__main__":
    build()
