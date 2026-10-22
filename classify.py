"""Auto-classify bookmarks saved by hand: reads Raindrop's Unsorted collection, asks the LLM to pick a
collection (existing first, new only if nothing fits) and add tags, then moves each bookmark.
Cheap when Unsorted is empty (a single API call). Result summary: state/classify_last.json."""
import os, re, json, time, requests
from pathlib import Path
from llm import ask
from news import parse_items

TOKEN = os.environ.get("RAINDROP_TOKEN", "").strip()
RD = "https://api.raindrop.io/rest/v1"
MAX_PER_RUN, BATCH, MAX_NEW_COLLECTIONS = 150, 30, 6
SKIP = Path("state/classify_skipped.json")

PROMPT = """You organize a person's saved web pages. Existing collections: {cols}

For each bookmark choose the best collection and 1-3 short tags (Chinese tags if the page is Chinese, otherwise English).
Rules: prefer an existing collection. Only if none fits reasonably, propose a new short collection name (2-6 Chinese characters or 1-3 English words); create as few new ones as possible and reuse a proposed name across items. If you cannot tell what the page is, use null.
Output only a JSON array, each element {{"i": number, "collection": "name or null", "tags": ["..."]}}.

Bookmarks:
"""


def api(method, path, payload=None):
    r = requests.request(method, RD + path, headers={"Authorization": f"Bearer {TOKEN}"}, json=payload, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Raindrop {r.status_code}: {r.text[:200]}")
    return r.json()


def main():
    if not TOKEN:
        print("RAINDROP_TOKEN not set")
        return
    skipped = set(json.loads(SKIP.read_text())) if SKIP.exists() else set()
    items, page = [], 0
    while len(items) < MAX_PER_RUN:
        got = api("GET", f"/raindrops/-1?perpage=50&page={page}").get("items", [])
        items += [x for x in got if x["_id"] not in skipped]
        if len(got) < 50:
            break
        page += 1
    items = items[:MAX_PER_RUN]
    if not items:
        print("Unsorted is empty")
        return

    cols = {c["title"]: c["_id"] for c in api("GET", "/collections").get("items", [])}
    status = {"candidates": len(items), "moved": 0, "new_collections": [], "unclear": 0, "errors": []}
    new_made = 0
    for s in range(0, len(items), BATCH):
        chunk = items[s:s + BATCH]
        lines = "\n".join(f"{i}. {x.get('title','')[:120]} | {x.get('domain','')} | {(x.get('excerpt') or '')[:200]}"
                          for i, x in enumerate(chunk))
        try:
            plan = parse_items(ask(PROMPT.format(cols=", ".join(cols) or "(none yet)") + lines, max_tokens=4000))
        except Exception as e:
            status["errors"].append(str(e)[:150])
            continue
        for a in plan:
            try:
                x = chunk[int(a["i"])]
            except Exception:
                continue
            name = a.get("collection")
            if not name or str(name).lower() == "null":
                skipped.add(x["_id"]); status["unclear"] += 1
                continue
            try:
                if name not in cols:
                    if new_made >= MAX_NEW_COLLECTIONS:
                        continue
                    cols[name] = api("POST", "/collection", {"title": name})["item"]["_id"]
                    new_made += 1
                    status["new_collections"].append(name)
                tags = list(dict.fromkeys((x.get("tags") or []) + [t for t in a.get("tags", []) if isinstance(t, str)]))[:6]
                api("PUT", f"/raindrop/{x['_id']}", {"collection": {"$id": cols[name]}, "tags": tags})
                status["moved"] += 1
                time.sleep(0.6)
            except Exception as e:
                status["errors"].append(str(e)[:150])
    SKIP.parent.mkdir(exist_ok=True)
    SKIP.write_text(json.dumps(sorted(skipped)[-3000:]))
    Path("state/classify_last.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
