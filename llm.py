"""共用:LLM 调用与 Bark 推送。环境变量: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, BARK_KEY"""
import os, requests

KEY = os.environ.get("LLM_API_KEY", "").strip()
BASE = (os.environ.get("LLM_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai").strip().rstrip("/")
MODELS = [m.strip() for m in (os.environ.get("LLM_MODEL") or "gemini-flash-lite-latest").split(",") if m.strip()]
BARK = os.environ.get("BARK_KEY", "").strip()


def ask(prompt, max_tokens=8000):
    last = None
    for m in MODELS:
        try:
            r = requests.post(f"{BASE}/chat/completions",
                              headers={"Authorization": f"Bearer {KEY}"},
                              json={"model": m, "messages": [{"role": "user", "content": prompt}],
                                    "max_tokens": max_tokens}, timeout=240)
            r.raise_for_status()
            txt = (r.json()["choices"][0]["message"]["content"] or "").strip()
            if txt:
                print(f"[llm] {m} ok")
                return txt
        except Exception as e:
            last = e
            print(f"[llm] {m} failed: {e}")
    raise RuntimeError(f"所有模型失败: {last}")


def split_bytes(text, limit=2800):
    """按段落切分,每段 UTF-8 不超过 limit 字节(Bark/APNs 单条上限约 4KB)。"""
    parts, cur = [], ""
    for para in text.split("\n"):
        while len(para.encode("utf-8")) > limit:
            cut = len(para)
            while len(para[:cut].encode("utf-8")) > limit:
                cut -= 20
            if cur:
                parts.append(cur); cur = ""
            parts.append(para[:cut]); para = para[cut:]
        if len((cur + "\n" + para).encode("utf-8")) > limit and cur:
            parts.append(cur); cur = para
        else:
            cur = (cur + "\n" + para) if cur else para
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def push_long(title, text, url="", group="学习讲义"):
    import time
    parts = split_bytes(text)
    for i, p in enumerate(parts, 1):
        t = title if len(parts) == 1 else f"{title} ({i}/{len(parts)})"
        push(t, p, url, group)
        time.sleep(2)


def push(title, body, url, group="学习讲义"):
    if not BARK:
        print("[bark] BARK_KEY 未设置,跳过推送")
        return
    data = {"device_key": BARK, "title": title, "body": body, "group": group}
    if url:
        data["url"] = url
    r = requests.post("https://api.day.app/push", json=data, timeout=30)
    print("[bark]", r.status_code)
