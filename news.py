"""科学快讯与论文:每小时读取权威来源的 RSS(轻量,无新条目则直接结束)。
新条目交给 LLM 打分和分类:
  - 分数 >= 3  → 自动存入 Raindrop 对应分类收藏夹(带类型、来源标签和中文摘要)
  - 分数 >= 4  → 同时推送到 Bark
首次运行(没有 state/news_seen.json)只入库 Raindrop,不推送 Bark。
运行结果写入 state/last_run.json,方便排查。"""
import re, json, os, datetime as dt, requests, xml.etree.ElementTree as ET
from pathlib import Path
from llm import ask, push_long

RTOKEN = os.environ.get("RAINDROP_TOKEN", "").strip()
RD = "https://api.raindrop.io/rest/v1"
FIELDS = ["天文与航天", "物理与化学", "生命科学", "心理与神经", "地球与气候", "技术与工程", "其他"]
PER_SOURCE = 12
BATCH = 30

SOURCES = [
    ("NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
    ("ESA", "https://www.esa.int/rssfeed/Our_Activities/Space_Science"),
    ("Science 新闻", "https://www.science.org/rss/news_current.xml"),
    ("Nature", "https://www.nature.com/nature.rss"),
    ("Nature Astronomy", "https://www.nature.com/natastron.rss"),
    ("Nature Human Behaviour", "https://www.nature.com/nathumbehav.rss"),
    ("Science Advances", "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv"),
    ("PNAS", "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas"),
    ("arXiv astro-ph", "https://rss.arxiv.org/rss/astro-ph"),
]

PROMPT = """你是科学新闻与文献编辑。下列条目可能是新闻、期刊论文或预印本。对每条给出:
- score(0-5):5=极其重要,4=重要(推送),3=值得收藏阅读,2及以下=不要。重大发现、航天任务成败、重要观测成果、影响领域的论文或综述给高分;产品宣传、评论、旧闻、常规增量论文给低分;预印本只有结论特别重要才给4以上。
- kind:"新闻"、"论文"、"综述"或"预印本"
- field:只能从这几个里选一个:天文与航天、物理与化学、生命科学、心理与神经、地球与气候、技术与工程、其他
- summary:中文2-3句,说明发生了什么或发现了什么、为什么重要。只依据给出的内容,不编造数据。
只输出 JSON 数组,元素 {"i":编号,"score":数字,"kind":"...","field":"...","summary":"..."},不要其他文字。

条目:
"""


def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def fetch_rss(url):
    root = ET.fromstring(requests.get(url, timeout=30, headers={"User-Agent": "news-bot/1.0"}).content)
    out = []
    for el in root.iter():
        if el.tag.split("}")[-1] not in ("item", "entry"):
            continue
        g = lambda n: next((x for x in el if x.tag.split("}")[-1] == n), None)
        t, d, l = g("title"), g("description") or g("summary"), g("link")
        link = ((l.get("href") or l.text or "") if l is not None else "").strip()
        if t is not None and link:
            out.append({"title": strip(t.text), "link": link, "text": strip(d.text if d is not None else "")[:600]})
    return out[:PER_SOURCE]


def parse_items(txt):
    """容错解析:逐个对象提取,修复非法转义,坏掉的对象跳过,不让整批失败。"""
    txt = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", txt)
    out = []
    for m in re.finditer(r"\{[^{}]*\}", txt, re.S):
        try:
            out.append(json.loads(m.group(0), strict=False))
        except Exception:
            continue
    return out


def score(items, status):
    keep = []
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        lines = "\n".join(f"{i}. [{x['source']}] {x['title']} — {x['text'][:300]}" for i, x in enumerate(chunk))
        try:
            txt = ask(PROMPT + lines, max_tokens=6000)
            arr = parse_items(txt)
            if not arr:
                raise RuntimeError("无法解析评分结果")
            for a in arr:
                try:
                    i, s = int(a["i"]), float(a.get("score", 0))
                except Exception:
                    continue
                if s >= 3 and 0 <= i < len(chunk):
                    f = a.get("field") if a.get("field") in FIELDS else "其他"
                    keep.append(dict(chunk[i], score=s, kind=str(a.get("kind", "新闻")), field=f,
                                     summary=str(a.get("summary", ""))[:300]))
        except Exception as e:
            status.setdefault("llm_errors", []).append(str(e)[:200])
            print("[score] 失败:", e)
    return keep


def rd(path, payload=None):
    h = {"Authorization": f"Bearer {RTOKEN}"}
    r = (requests.post(RD + path, headers=h, json=payload, timeout=60) if payload is not None
         else requests.get(RD + path, headers=h, timeout=60))
    if r.status_code >= 400:
        raise RuntimeError(f"Raindrop {r.status_code}: {r.text[:200]}")
    return r.json()


def to_raindrop(keep, status):
    if not RTOKEN:
        status["raindrop"] = "RAINDROP_TOKEN 未设置"
        return
    try:
        cols = {c["title"]: c["_id"] for c in rd("/collections").get("items", [])}
        for f in {k["field"] for k in keep}:
            if f not in cols:
                cols[f] = rd("/collection", {"title": f})["item"]["_id"]
        rd("/raindrops", {"items": [{
            "link": k["link"], "title": k["title"][:200], "excerpt": k["summary"],
            "tags": [k["kind"], k["source"]], "collection": {"$id": cols[k["field"]]}} for k in keep]})
        status["raindrop"] = f"ok, 添加 {len(keep)} 条"
    except Exception as e:
        status["raindrop"] = f"失败: {e}"
        print("[raindrop]", e)


def main():
    p = Path("state/news_seen.json")
    first = not p.exists()
    seen = set() if first else set(json.loads(p.read_text(encoding="utf-8")))
    status = {"time": (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"), "sources": {}}
    items, got = [], set()
    for name, url in SOURCES:
        try:
            rows = fetch_rss(url)
            status["sources"][name] = len(rows)
        except Exception as e:
            status["sources"][name] = f"失败: {str(e)[:80]}"
            continue
        for r in rows:
            if r["link"] not in seen and r["link"] not in got:
                got.add(r["link"])
                items.append(dict(r, source=name))
    status["new_items"] = len(items)
    Path("state").mkdir(exist_ok=True)

    keep = score(items, status) if items else []
    status["kept"] = len(keep)

    if keep:
        to_raindrop(keep, status)
        store = Path("state/news.json")
        hist = json.loads(store.read_text(encoding="utf-8")) if store.exists() else []
        hist = (hist + [{"time": status["time"], "source": k["source"], "kind": k["kind"], "field": k["field"],
                         "title": k["title"], "link": k["link"], "score": k["score"], "summary": k["summary"]}
                        for k in keep])[-500:]
        store.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
        push_items = [k for k in keep if k["score"] >= 4]
        if push_items and not first:
            body = "\n\n".join(f"【{k['kind']}·{k['source']}】{k['title'][:100]}\n{k['summary']}\n{k['link']}" for k in push_items)
            push_long(f"科学快讯 {len(push_items)} 条", body, "", group="科学快讯")
            status["pushed"] = len(push_items)

    # 评分失败的批次不记入 seen,下次重试;其余全部记入
    if not status.get("llm_errors"):
        p.write_text(json.dumps(sorted(seen | got)[-5000:], ensure_ascii=False), encoding="utf-8")
    if items or status.get("llm_errors"):
        Path("state/last_run.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
