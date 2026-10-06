"""长期学习引擎。所有进度存在仓库里的 state/state.json(由 GitHub Actions 自动提交),
不依赖 Raindrop 或任何第三方的数据格式,几个月后依然可以读、可以迁移。

四个时段(由 study.yml 的定时任务触发):
  --slot ielts    雅思微练习(难度跟随当前阶段目标分数)
  --slot subject  学科微卡:每天一张,科目轮换,每章 5 张,章节自动推进
  --slot review   间隔复习:最多 4 题,到期的卡片按 1/4/14/45 天复习
  --slot report   每周小结:本周完成量、教材进度、预计完成时间、雅思阶段检查点
默认只预览(不写状态、不推送),加 --apply 才执行。

环境变量:LLM_API_KEY、BARK_KEY(可选 LLM_BASE_URL、LLM_MODEL,默认智谱 glm-4-flash)
新增科目:在 study_data.py 的 BOOKS 里加一项即可。
"""
import os, sys, re, json, time, datetime as dt
from pathlib import Path
import requests
from study_data import BOOKS, ielts_stage

LLM_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_URL = (os.environ.get("LLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4").strip().rstrip("/")
LLM_MODEL = (os.environ.get("LLM_MODEL") or "glm-4-flash").strip()
APPLY = "--apply" in sys.argv
SLOT = sys.argv[sys.argv.index("--slot") + 1] if "--slot" in sys.argv else "subject"
TODAY = (dt.date.fromisoformat(os.environ["STUDY_TODAY"])
         if os.environ.get("STUDY_TODAY") else dt.date.today())
STATE_PATH = Path("state/state.json")
SEP = "====="
CARDS_PER_CHAPTER = 5
INTERVALS = [1, 4, 14, 45]   # 复习间隔(天)。每张卡复习 4 次后毕业
REVIEW_PER_SLOT = 4          # 一次复习最多几题(约 3 分钟)
MAX_OVERDUE = 14             # 过期超过这么多天不追补,顺延


# ---------- 状态 ----------
def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"version": 1, "started": TODAY.isoformat(),
            "subjects": {}, "chapters": {}, "cards": {}, "log": []}


def save_state(state):
    if not APPLY:
        return
    state["log"] = state["log"][-600:]
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def log(state, slot, ref=""):
    state["log"].append({"date": TODAY.isoformat(), "slot": slot, "ref": str(ref)})


def subject_state(state, subj):
    return state["subjects"].setdefault(subj, {"chapter": 1, "card": 0})


def finished(state, subj):
    return subject_state(state, subj)["chapter"] > len(BOOKS[subj]["chapters"])


def cards_done(state, subj):
    st = subject_state(state, subj)
    return min((st["chapter"] - 1) * CARDS_PER_CHAPTER + st["card"],
               len(BOOKS[subj]["chapters"]) * CARDS_PER_CHAPTER)


def today_subject(state):
    active = [s for s in BOOKS if not finished(state, s)]
    return active[TODAY.toordinal() % len(active)] if active else None


# ---------- 模型与推送 ----------
def ask_llm(prompt):
    delays = [10, 30, 60, 90]  # 限速或服务繁忙时的重试等待(秒)
    for attempt in range(len(delays) + 1):
        r = requests.post(
            f"{LLM_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_KEY}"},
            json={"model": LLM_MODEL, "temperature": 0.4,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=180,
        )
        if r.status_code in (429, 500, 502, 503, 504) and attempt < len(delays):
            print(f"模型接口暂时不可用({r.status_code}),{delays[attempt]} 秒后重试")
            time.sleep(delays[attempt])
            continue
        if r.status_code >= 400:
            print(f"模型接口报错 {r.status_code}: " + " ".join(r.text.split())[:400])
            key_info = "未设置(空)" if not LLM_KEY else f"长度 {len(LLM_KEY)},以 AIza 开头:{LLM_KEY.startswith('AIza')}"
            print(f"当前使用的接口:{LLM_URL},模型:{LLM_MODEL},LLM_API_KEY:{key_info}")
            if r.status_code in (401, 403):
                print("提示:key 与接口必须是同一家的。Gemini 的 key 要配 Gemini 的 LLM_BASE_URL 和 LLM_MODEL")
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    raise RuntimeError("一直被限速")


def bark(title, body):
    print(f"\n【{title}】\n{body}\n")
    if APPLY:
        if not os.environ.get("BARK_KEY"):  # 没法推送就中止,避免进度在你看不到的情况下推进
            sys.exit("BARK_KEY 未设置:无法推送,本次中止")
        requests.post("https://api.day.app/push", json={
            "device_key": os.environ["BARK_KEY"], "title": title,
            "body": body, "group": "study"}, timeout=30).raise_for_status()
    else:
        print("(预览:没有推送)")


def parse_qa(card):
    q = re.search(r"问题[：:](.*?)(?=答案[：:]|$)", card, re.S)
    a = re.search(r"答案[：:](.*)", card, re.S)
    return (q.group(1).strip() if q else card.strip(),
            a.group(1).strip() if a else "")


def fmt_card(card):
    m = re.search(r"答案[：:]", card)
    if not m:
        return card.strip()
    return f"{card[:m.start()].strip()}\n\n· · · 想好了再往下滑 · · ·\n\n\n\n{card[m.start():].strip()}"


def split_cards(text):
    parts = re.split(r"(?m)^\s*(?:={3,}|-{3,}|\*{3,})\s*$", text)
    cards = [p.strip() for p in parts if "要点" in p]
    if len(cards) < 3:  # 模型没写分隔线时,按"要点:"开头拆
        parts = re.split(r"(?m)^(?=\W{0,6}要点\s*[\uff1a:])", text)
        cards = [p.strip() for p in parts if "要点" in p]
    return [re.sub(r"[*#`]", "", c).strip() for c in cards][:CARDS_PER_CHAPTER]


def gen_cards(book, n, en, zh):
    text = ask_llm(
        f"你是大学助教。学生自学《{book['name']}》第{n}章「{en}」(中文:{zh})。\n"
        f"请把本章拆成 {CARDS_PER_CHAPTER} 张微卡,每张 3 分钟内能读完。"
        f"卡与卡之间单独一行写 {SEP}。每张格式严格如下:\n"
        "要点:(中文,不超过 100 字,只讲一个知识点,通俗易懂)\n"
        "关键词:(1~2 个,英文 - 中文)\n"
        "问题:(一个能用一句话回答的问题)\n"
        "答案:(一句话)\n"
        "只写你有把握的内容,不确定就不要编造。不要写任何其他文字。")
    cards = split_cards(text)
    if len(cards) < 3:
        print("模型原始返回(用于排查格式问题):\n" + text[:800])
    return cards


# ---------- 四个时段 ----------
def slot_subject(state):
    subj = today_subject(state)
    if not subj:
        print("全部教材已完成 🎉")
        return
    book, st = BOOKS[subj], subject_state(state, subj)
    n = st["chapter"]
    en, zh = book["chapters"][n - 1]
    key = f"{subj}-{n}"
    if key not in state["chapters"]:
        cards = gen_cards(book, n, en, zh)
        if len(cards) < 3:
            sys.exit(f"{key} 微卡生成失败,稍后重试")
        state["chapters"][key] = cards
    cards = state["chapters"][key]
    k = st["card"]
    bark(f"{subj} · 第{n}章 {zh} · {k + 1}/{len(cards)}",
         fmt_card(cards[k]) + "\n\n(AI 生成,以教材原文为准)")
    state["cards"][f"{key}-{k + 1}"] = {
        "label": f"{subj} 第{n}章 {zh}", "text": cards[k], "stage": 0,
        "due": (TODAY + dt.timedelta(days=INTERVALS[0])).isoformat()}
    st["card"] += 1
    if st["card"] >= len(cards):  # 本章结束,进入下一章,清掉已不需要的章节缓存
        st["chapter"] += 1
        st["card"] = 0
        del state["chapters"][key]
    log(state, "subject", f"{key}-{k + 1}")


def slot_review(state):
    today = TODAY.isoformat()
    due = []
    for cid, c in sorted(state["cards"].items(), key=lambda kv: kv[1].get("due") or "9"):
        if not c.get("due") or c["due"] > today:
            continue
        overdue = (TODAY - dt.date.fromisoformat(c["due"])).days
        if overdue > MAX_OVERDUE:  # 积压太久不追补,顺延一周
            c["due"] = (TODAY + dt.timedelta(days=7)).isoformat()
        else:
            due.append(cid)
    picked = due[:REVIEW_PER_SLOT]
    if not picked:
        print("今天没有到期的复习卡")
        return
    qs, ans = [], []
    for i, cid in enumerate(picked, 1):
        c = state["cards"][cid]
        q, a = parse_qa(c["text"])
        qs.append(f"{i}. {q}\n   ({c['label']})")
        ans.append(f"{i}. {a}")
        c["stage"] += 1
        c["due"] = (None if c["stage"] >= len(INTERVALS) else
                    (TODAY + dt.timedelta(days=INTERVALS[c["stage"]])).isoformat())
    bark(f"复习 · {len(picked)} 题",
         "\n\n".join(qs) + "\n\n· · · 想好了再往下滑 · · ·\n\n\n\n" + "\n".join(ans))
    log(state, "review", len(picked))


def slot_ielts(state):
    band, _ = ielts_stage(TODAY)
    subj = today_subject(state)
    topic = (BOOKS[subj]["chapters"][subject_state(state, subj)["chapter"] - 1][0]
             if subj else "Space and the Universe")
    text = ask_llm(
        f"写一段原创的雅思学术阅读风格短文,英文,70-90 词,主题:{topic}。\n"
        f"难度相当于雅思 {band} 分(考生正在向这个分数冲刺),避免过于生僻的词。\n"
        "然后依次给出:1 道判断题(TRUE / FALSE / NOT GIVEN)、3 个值得学的词(英文 - 中文)。\n"
        "最后另起一行写「—— 答案 ——」,再给判断题答案和一句话解析。\n"
        "整个过程要能在 3 分钟内完成。纯文本,不要其他内容。")
    bark(f"雅思 · {TODAY:%m-%d}", text)
    log(state, "ielts", band)


def slot_report(state):
    since = (TODAY - dt.timedelta(days=7)).isoformat()
    week = [e for e in state["log"] if e["date"] > since]
    new = sum(e["slot"] == "subject" for e in week)
    rev = sum(int(e["ref"]) for e in week if e["slot"] == "review")
    ielts = sum(e["slot"] == "ielts" for e in week)
    lines = [f"本周:新学 {new} 张微卡,复习 {rev} 题,雅思练习 {ielts} 次"]
    remaining = 0
    for subj, book in BOOKS.items():
        total = len(book["chapters"]) * CARDS_PER_CHAPTER
        done = cards_done(state, subj)
        remaining += total - done
        lines.append(f"{subj}:{done}/{total} 张")
    if remaining:
        eta = TODAY + dt.timedelta(days=remaining)
        lines.append(f"按每天 1 张,预计 {eta:%Y 年 %m 月}学完全部教材")
    band, by = ielts_stage(TODAY)
    left = (dt.date.fromisoformat(by) - TODAY).days
    lines.append(f"雅思:当前阶段目标 {band} 分,检查点 {by}"
                 + (f"(还有 {left} 天),到时请做一套完整模考核对真实水平" if left >= 0 else ""))
    bark("每周小结", "\n".join(lines))
    log(state, "report")


SLOTS = {"subject": slot_subject, "review": slot_review,
         "ielts": slot_ielts, "report": slot_report}

if SLOT not in SLOTS:
    sys.exit("--slot 只能是 subject / review / ielts / report")
state = load_state()
SLOTS[SLOT](state)
save_state(state)
