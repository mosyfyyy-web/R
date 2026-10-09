"""科学快讯(新闻、期刊论文、预印本):每小时读取权威来源的 RSS(很轻量)。只有新条目才交给 LLM 打分,
仅重要性 >= 4 的条目写入 state/news.json 并推送。首次运行只记录,不推送。"""
import re, json, datetime as dt, requests, xml.etree.ElementTree as ET
from pathlib import Path
from llm import ask, push_long

SOURCES = [
    # 新闻与机构发布
    ("NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
    ("ESA", "https://www.esa.int/rssfeed/Our_Activities/Space_Science"),
    ("Science 新闻", "https://www.science.org/rss/news_current.xml"),
    # 期刊(论文)
    ("Nature", "https://www.nature.com/nature.rss"),
    ("Nature Astronomy", "https://www.nature.com/natastron.rss"),
    ("Nature Human Behaviour", "https://www.nature.com/nathumbehav.rss"),
    ("Science Advances", "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv"),
    ("PNAS", "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas"),
    # 预印本
    ("arXiv astro-ph", "https://rss.arxiv.org/rss/astro-ph"),
]

SCORE_PROMPT = """你是科学新闻编辑。条目可能是新闻,也可能是期刊论文或预印本。判断是否值得推送:重大发现、航天任务的成功或失败、重大观测成果、对本领域有重要影响的论文或综述、权威研究的重要突破。
普通新闻、产品宣传、旧闻、评论、常规的增量式论文一律低分。预印本(arXiv)只有结论特别重要时才给 4 分以上。
对每条给出 score(0-5,5=极其重要,4=重要,3及以下=不推送)和 kind("新闻"或"论文"或"综述"或"预印本")和 summary(中文2-3句,说明发生了什么或论文发现了什么、为什么重要,只依据给出的内容,不编造数据)。
只输出 JSON 数组,元素格式 {"i":编号,"score":数字,"kind":"...","summary":"..."},不要其他文字。

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
    return out[:20]


def score(items):
    lines = "\n".join(f"{i}. [{x['source']}] {x['title']} — {x['text'][:300]}" for i, x in enumerate(items))
    try:
        txt = ask(SCORE_PROMPT + lines, max_tokens=3000)
    except Exception as e:
        print("[score] 跳过:", e)
        return []
    m = re.search(r"\[.*\]", txt, re.S)
    out = []
    for a in (json.loads(m.group(0)) if m else []):
        try:
            i, s = int(a["i"]), float(a.get("score", 0))
        except Exception:
            continue
        if s >= 4 and 0 <= i < len(items):
            out.append(dict(items[i], score=s, kind=str(a.get("kind", "新闻")), summary=str(a.get("summary", ""))[:300]))
    return out


def main():
    p = Path("state/news_seen.json")
    first = not p.exists()
    seen = set() if first else set(json.loads(p.read_text(encoding="utf-8")))
    items, got = [], set()
    for name, url in SOURCES:
        try:
            rows = fetch_rss(url)
            print(f"[ok] {name} {len(rows)}")
        except Exception as e:
            print(f"[skip] {name}: {e}")
            continue
        for r in rows:
            if r["link"] not in seen and r["link"] not in got:
                got.add(r["link"])
                items.append(dict(r, source=name))
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(sorted(seen | got)[-5000:], ensure_ascii=False), encoding="utf-8")

    if first:
        print("首次运行:只记录,不推送")
        return
    if not items:
        print("无新条目")
        return
    keep = score(items)
    print("重要条目", len(keep))
    if not keep:
        return

    store = Path("state/news.json")
    hist = json.loads(store.read_text(encoding="utf-8")) if store.exists() else []
    now = (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    hist = (hist + [{"time": now, "source": k["source"], "kind": k["kind"], "title": k["title"], "link": k["link"],
                     "score": k["score"], "summary": k["summary"]} for k in keep])[-300:]
    store.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    body = "\n\n".join(f"【{k['kind']}·{k['source']}】{k['title'][:100]}\n{k['summary']}\n{k['link']}" for k in keep)
    push_long(f"科学快讯 {len(keep)} 条", body, "", group="科学快讯")


if __name__ == "__main__":
    main()
