#!/usr/bin/env python3
"""Build Capitol Notes: fetch political RSS feeds, cluster duplicate stories,
rank by how many outlets ran them, and render index.html. Standard library only."""
import html, json, re, sys, urllib.request, concurrent.futures as cf
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

CFG = json.load(open("feeds.json"))
UA = {"User-Agent": "Mozilla/5.0 (compatible; CapitolNotes/1.0)"}
MAX_AGE = timedelta(hours=CFG.get("max_age_hours", 36))
STOP = set("a an the of in on at to for and or as is are was were be by with from after over amid says say said new its it his her their this that will not no up out into than".split())

def gnews(q):  # Google News RSS search feed
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:1d") + "&hl=en-US&gl=US&ceid=US:en"
import urllib.parse

def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return ET.fromstring(r.read())
    except Exception as e:
        print("feed failed:", url, e, file=sys.stderr)
        return None

def parse(root, default_source):
    out = []
    if root is None: return out
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        src = (src_el.text if src_el is not None and src_el.text else default_source) or "Unknown"
        if src_el is not None and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            when = parsedate_to_datetime(it.findtext("pubDate"))
            if when.tzinfo is None: when = when.replace(tzinfo=timezone.utc)
        except Exception:
            when = datetime.now(timezone.utc)
        if title and link:
            out.append({"title": html.unescape(title), "link": link, "source": src.strip(), "when": when})
    return out

def tokens(t):
    return {w for w in re.findall(r"[a-z0-9']+", t.lower()) if w not in STOP and len(w) > 2}

def cluster(items):
    """Greedy clustering by title-token overlap."""
    groups = []
    for it in sorted(items, key=lambda x: x["when"], reverse=True):
        tk = tokens(it["title"]); it["tk"] = tk
        for g in groups:
            inter = len(tk & g["tk"]); union = len(tk | g["tk"]) or 1
            if inter / union >= 0.5 or (inter >= 4 and inter / min(len(tk), len(g["tk"])) >= 0.6):
                g["items"].append(it); g["tk"] |= tk; break
        else:
            groups.append({"items": [it], "tk": set(tk)})
    for g in groups:
        outlets = sorted({i["source"] for i in g["items"]})
        # prefer a direct (non-redirect) link, then the longest headline
        best = sorted(g["items"], key=lambda i: ("news.google.com" in i["link"], -len(i["title"])))[0]
        g.update(outlets=outlets, score=len(outlets), title=best["title"], link=best["link"], when=max(i["when"] for i in g["items"]))
    return groups

def load(feeds):
    jobs = []
    for f in feeds:
        url = gnews(f["q"]) if "q" in f else f["url"]
        jobs.append((url, f.get("name", "")))
    with cf.ThreadPoolExecutor(8) as ex:
        roots = list(ex.map(lambda j: fetch(j[0]), jobs))
    items = []
    for (url, name), root in zip(jobs, roots):
        items += parse(root, name)
    now = datetime.now(timezone.utc)
    return [i for i in items if now - i["when"] <= MAX_AGE], len(jobs), sum(r is not None for r in roots)

def esc(s): return html.escape(s, quote=True)

def link(g, cls="", upper=False):
    t = g["title"]
    if len(t) > 140: t = t[:137].rstrip() + "..."
    elif not upper: t += "..."
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{esc(g["link"])}" title="{esc(", ".join(g["outlets"]))}" rel="noopener">{esc(t)}</a>'

def main():
    sections, ok_total, n_total = {}, 0, 0
    for key in ("top", "washington", "world", "justice", "elections"):
        feeds = CFG["sections"].get(key, [])
        items, n, ok = load(feeds); ok_total += ok; n_total += n
        sections[key] = [g for g in cluster(items)]
        sections[key].sort(key=lambda g: (g["score"], g["when"]), reverse=True)
    used, chosen = set(), []
    GENERIC = set("trump president administration house senate congress republican republicans democrats democratic white federal court national says american americans state states over amid report reports".split())
    def topic(t): return {w for w in tokens(t) if w not in GENERIC and len(w) > 3}
    def take(key, n):
        out = []
        need = 1 if key == "top" else 2  # shared topical words that mark a duplicate story
        for g in sections[key]:
            if g["link"] in used: continue
            tk = topic(g["title"])
            if any(len(tk & c) >= min(need, len(tk), len(c)) and tk & c for c in chosen): continue
            used.add(g["link"]); chosen.append(tk); out.append(g)
            if len(out) == n: break
        return out
    lead = take("top", 2); tl = take("top", 4)
    media = take("elections", CFG.get("elections_count", 10))
    cols = {k: take(k, CFG.get("column_count", 15)) for k in ("washington", "world", "justice")}
    def col(gs):
        h = []
        for i, g in enumerate(gs):
            cls = "hot" if i == 0 else ("it" if g["score"] <= 1 and i % 4 == 3 else "")
            h.append(link(g, cls))
            if i in (4, 9): h.append("<hr>")
        return "\n".join(h)
    ct = datetime.now(ZoneInfo(CFG.get("timezone", "America/Chicago")))
    page = open("template.html", encoding="utf-8").read()
    page = (page.replace("{{TL}}", "\n".join(link(g, upper=True) for g in tl))
                .replace("{{LEAD}}", "\n".join(link(g, "hot" if i == 0 else "", upper=True) for i, g in enumerate(lead)))
                .replace("{{MEDIA_TITLE}}", esc(CFG.get("elections_title", "CAMPAIGNS & CONGRESS")))
                .replace("{{MEDIA}}", "\n".join(link(g) for g in media))
                .replace("{{COL1}}", col(cols["washington"])).replace("{{COL2}}", col(cols["world"])).replace("{{COL3}}", col(cols["justice"]))
                .replace("{{FOOT}}", f'{ct:%A, %B %-d, %Y} · updated {ct:%-I:%M %p} · {ok_total} of {n_total} feeds reporting. Headlines link to the original outlets.'))
    if ok_total == 0:
        sys.exit("all feeds failed; leaving the existing page untouched")
    open("index.html", "w", encoding="utf-8").write(page)
    print("built", ct.isoformat(), "feeds", ok_total, "/", n_total)

if __name__ == "__main__":
    main()
