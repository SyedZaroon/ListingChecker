#!/usr/bin/env python3
"""Fast product checker (filter-aware). Writes results.json.

Usage:
  python3 check_products.py urls.txt        # check all URLs in the file
  python3 check_products.py --one "URL"     # test a single URL and show details
Needs only Python 3.8+ (no extra packages).
"""
import json, re, sys, gzip
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit

WORKERS = 20
TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
           "Accept-Language": "en-GB,en;q=0.9", "Accept-Encoding": "gzip"}

EMPTY_RE = re.compile(
    r"no products (?:found|match|were found)|no results (?:found|for|match)|"
    r"nothing (?:found|matched|matches)|no items found|"
    r"(?<![\d,.])0 (?:products|results|items)\b|couldn.t find any products", re.I)
HANDLE_RE = re.compile(r'href=["\'](?:https?://[^"\'/]+)?/(?:collections/[^/"\']+/)?products/([^"\'?#/]+)', re.I)

def get(url):
    with urlopen(Request(url, headers=HEADERS), timeout=TIMEOUT) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", "ignore")

def feed_count(url):
    """No filters in URL -> count via Shopify products.json feed."""
    p = urlsplit(url)
    base = urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))
    total = 0
    for page in range(1, 11):
        data = json.loads(get(f"{base}/products.json?limit=250&page={page}"))
        n = len(data.get("products", []))
        total += n
        if n < 250:
            break
    return total

def page_count(url):
    """Filters in URL -> read the real page HTML (query string kept)."""
    html = get(url)
    m = re.search(r"<main\b.*?</main>", html, re.S | re.I)
    body = m.group(0) if m else html
    body = re.sub(r"<(script|style|template|noscript)\b.*?</\1>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", body)
    hit = EMPTY_RE.search(text)
    handles = set(HANDLE_RE.findall(body))
    if hit:
        return 0, f"empty message: '{hit.group(0)}'"
    return len(handles), f"{len(handles)} product links in page"

def check(url):
    has_query = bool(urlsplit(url).query)
    try:
        if has_query:
            n, note = page_count(url)
            return {"url": url, "count": n, "method": "page-html", "note": note}
        return {"url": url, "count": feed_count(url), "method": "products.json"}
    except Exception:
        pass
    try:
        n, note = page_count(url)
        return {"url": url, "count": n, "method": "page-html", "note": note}
    except Exception as e:
        return {"url": url, "count": None, "method": "error", "error": str(e)}

def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        print(json.dumps(check(sys.argv[2]), indent=2)); return
    path = sys.argv[1] if len(sys.argv) > 1 else "urls.txt"
    urls = [u.strip() for u in open(path) if u.strip().startswith("http")]
    results, done = {}, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(check, u) for u in urls]
        for f in as_completed(futures):
            r = f.result(); results[r["url"]] = r; done += 1
            print(f"[{done}/{len(urls)}] {r['count']!s:>5}  {r['url'][:100]}", flush=True)
    ordered = [results[u] for u in urls]
    json.dump(ordered, open("results.json", "w"), indent=2)
    print(f"\nDone. {sum(r['count']==0 for r in ordered)} empty, "
          f"{sum(r['count'] is None for r in ordered)} errors. Saved results.json")

if __name__ == "__main__":
    main()