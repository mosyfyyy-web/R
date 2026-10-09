"""每天抓取天文学/心理学最新文章 -> Gemini 筛选+打标签 -> 自动存进 Raindrop 对应收藏夹。
只用标准库。需要环境变量: RAINDROP_TOKEN, LLM_API_KEY, 可选 LLM_MODEL(逗号分隔回退列表)。
"""
import json, os, re, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET

RD = "https://api.raindrop.io/rest/v1"
RTOKEN = os.environ.get("RAINDROP_TOKEN", "")
BARK = os.environ.get("BARK_KEY", "")
PUSH_MAX = 5  # 每天最多推几条到 Bark
GKEY = os.environ.get("LLM_API_KEY", "")
MODELS = [m.strip() for m in os.environ.get(
    "LLM_MODEL",
    "gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.5-flash").split(",") if m.strip()]
SEEN_FILE = "state/seen.json"
MAX_PER_SUBJECT = 8  # 每天每科最多收几篇，避免刷屏

SOURCES = {
    "天文学": [
        ("rss", "https://phys.org/rss-feed/space-news/astronomy/"),
        ("rss", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
        ("arxiv", "cat:astro-ph.GA OR cat:astro-ph.CO OR cat:astro-ph.EP"),
    ],
    "心理学": [
        ("rss", "https://www.sciencedaily.com/rss/mind_brain/psychology.xml"),
        ("rss", "https://www.frontiersin.org/journals/psychology/rss"),
        ("rss", "https://phys.org/rss-feed/biology-news/neuroscience/"),
    ],
}


def http(url, data=None, headers=None, method=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    req.add_header("User-Agent", "raindrop-feed/1.0")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def fetch_rss(url):
    out = []
    root = ET.fromstring(http(url))
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        g = lambda n: next((c for c in it if c.tag.split("}")[-1] == n), None)
        t, d = g("title"), g("description") or g("summary")
        l = g("link")
        link = (l.get("href") if l is not None and l.get("href") else (l.text if l is not None else "")) or ""
        if t is not None and link.strip():
            out.append({"title": strip(t.text), "link": link.strip(), "text": strip(d.text if d is not None else "")[:400]})
    return out[:15]


def fetch_arxiv(query):
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": query, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": 10})
    return fetch_rss(url)


def collect():
    items = []
    for subject, srcs in SOURCES.items():
        for kind, ref in srcs:
            try:
                got = fetch_rss(ref) if kind == "rss" else fetch_arxiv(ref)
                items += [dict(i, subject=subject) for i in got]
                print(f"[ok] {subject} {ref[:60]} -> {len(got)}")
            except Exception as e:
                print(f"[skip] {subject} {ref[:60]}: {e}")
    return items


def llm_pick(items):
    """返回 {index: {"tags": [...], "note": "..."}}；失败则返回 None（调用方回退为不筛选）。"""
    if not GKEY or not items:
        return None
    lines = [f"{i}. [{x['subject']}] {x['title']} — {x['text'][:150]}" for i, x in enumerate(items)]
    prompt = (
        "你是学习资料筛选助手。读者是中文学习者，英语约雅思5.5，想系统学天文学和心理学。\n"
        "从下列条目中挑出适合初学者阅读、有实质内容的（排除广告、纯新闻快讯、过于专业的论文）。\n"
        "只输出JSON数组，每个元素: {\"i\":编号,\"tags\":[1-3个中文标签],\"note\":\"一句中文说明，20字内\"}。\n\n"
        + "\n".join(lines))
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json"}}).encode()
    for m in MODELS:
        for wait in (0, 10, 30):
            time.sleep(wait)
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GKEY}"
                res = json.loads(http(url, body, {"Content-Type": "application/json"}, "POST", timeout=90))
                txt = res["candidates"][0]["content"]["parts"][0]["text"]
                arr = json.loads(re.sub(r"^```json|```$", "", txt.strip()))
                print(f"[llm] {m} ok, kept {len(arr)}")
                return {int(a["i"]): a for a in arr}
            except urllib.error.HTTPError as e:
                print(f"[llm] {m} HTTP {e.code}")
                if e.code in (404, 400, 403):
                    break  # 换下一个模型
            except Exception as e:
                print(f"[llm] {m} {type(e).__name__}: {e}")
    return None


def rd(path, payload=None, method=None):
    h = {"Authorization": f"Bearer {RTOKEN}", "Content-Type": "application/json"}
    data = json.dumps(payload).encode() if payload is not None else None
    return json.loads(http(RD + path, data, h, method or ("POST" if data else "GET")))


def collection_ids():
    have = {c["title"]: c["_id"] for c in rd("/collections").get("items", [])}
    for s in SOURCES:
        if s not in have:
            have[s] = rd("/collection", {"title": s})["item"]["_id"]
    return have


def push_bark(chosen):
    if not BARK:
        print("[bark] BARK_KEY 未设置，跳过推送")
        return
    for c in chosen[:PUSH_MAX]:
        try:
            body = json.dumps({"device_key": BARK, "title": f"【{c['subject']}】{c['title'][:60]}",
                               "body": c["note"], "url": c["link"], "group": "每日资料"}).encode()
            http("https://api.day.app/push", body, {"Content-Type": "application/json; charset=utf-8"}, "POST")
            print(f"[bark] pushed {c['title'][:40]}")
        except Exception as e:
            print(f"[bark FAIL] {type(e).__name__}: {e}")


def main():
    os.makedirs("state", exist_ok=True)
    seen = set(json.load(open(SEEN_FILE))) if os.path.exists(SEEN_FILE) else set()
    items = [i for i in collect() if i["link"] not in seen]
    dedup, uniq = set(), []
    for i in items:
        if i["link"] not in dedup:
            dedup.add(i["link"]); uniq.append(i)
    items = uniq
    print(f"new candidates: {len(items)}")
    if not items:
        return

    picks = llm_pick(items)
    chosen, count = [], {}
    for idx, it in enumerate(items):
        if picks is not None and idx not in picks:
            continue
        if count.get(it["subject"], 0) >= MAX_PER_SUBJECT:
            continue
        count[it["subject"]] = count.get(it["subject"], 0) + 1
        p = (picks or {}).get(idx, {})
        it["tags"] = [it["subject"], "待读"] + [t for t in p.get("tags", []) if isinstance(t, str)][:3]
        it["note"] = p.get("note") or it["text"][:120]
        chosen.append(it)

    if RTOKEN and chosen:
        try:
            cols = collection_ids()
            rd("/raindrops", {"items": [{
                "link": c["link"], "title": c["title"][:200], "excerpt": c["note"],
                "tags": c["tags"], "collection": {"$id": cols[c["subject"]]}, "pleaseParse": {}}
                for c in chosen]})
            print(f"added to Raindrop: {len(chosen)}")
        except Exception as e:
            print(f"[raindrop FAIL] {type(e).__name__}: {e}")
    elif not RTOKEN:
        print("[raindrop] RAINDROP_TOKEN 未设置，跳过收藏")

    push_bark(chosen)

    seen |= {i["link"] for i in items}  # 没选中的也记住，避免明天重复判断
    json.dump(sorted(seen)[-3000:], open(SEEN_FILE, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
