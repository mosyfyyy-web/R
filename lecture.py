"""每日讲义:按 study_data.BOOKS 的章节顺序,每次生成一章完整讲义,存入 lectures/,
推送摘要 + 讲义链接到 Bark。天文学与心理学隔天交替。"""
import re, sys, json, datetime as dt
from pathlib import Path
from study_data import BOOKS
from llm import ask, push, KEY

REPO = "mosyfyyy-web/R"
TODAY = dt.date.today()
PROG = Path("state/lecture_progress.json")
OUT = Path("lectures")

REFS = {
    "天文学": "OpenStax《Astronomy 2e》(免费开放教材) 与 Chaisson & McMillan《Astronomy Today》(Pearson)",
    "心理学": "OpenStax《Psychology 2e》(免费开放教材) 与 Gerrig & Zimbardo《Psychology and Life》(Pearson)",
}

PROMPT = """你是一位大学教授,正在给专业学习者上完整的一次课。请写本次课的讲义。

章节:OpenStax《{book}》第 {n} 章「{en}」(中文:{zh})。
可参照的教材:{refs}。请指出 Pearson 等其他教材中对应的章节主题(只写主题,不要编造页码)。

要求:
1. 用中文,用你自己的语言讲解,不要逐字照搬任何教材原文。
2. 专业水平,讲清推导、机制和数量级,例子要具体。
3. 严格使用以下 Markdown 结构:
## 本讲摘要
(3句话,概括本章最重要的结论)
## 学习目标
(3-5条)
## 讲解
(分3-5个小节,每节讲清概念、推导或机制)
## 关键公式与术语
(列表;公式用 LaTeX 行内写法 $...$)
## 常见误区
(2-3条,说明错在哪、正确理解是什么)
## 与其他教材的对应
(列出可对照的 Pearson 等教材章节主题)
## 延伸阅读
(只推荐你确信存在的权威来源,写书名或机构名即可,不要编造网址)
## 小结
(一段话)

全文约2000-3000字。
"""


def extract_summary(text):
    m = re.search(r"## 本讲摘要\s*(.+?)(?=\n## |\Z)", text, re.S)
    return (m.group(1) if m else text[:200]).strip()[:300]


def main():
    if not KEY:
        sys.exit("LLM_API_KEY 未设置")
    subj = ["天文学", "心理学"][TODAY.toordinal() % 2]
    book, chapters = BOOKS[subj]["name"], BOOKS[subj]["chapters"]
    prog = json.loads(PROG.read_text(encoding="utf-8")) if PROG.exists() else {}
    idx = prog.get(subj, 0) % len(chapters)
    en, zh = chapters[idx]
    n = idx + 1

    text = ask(PROMPT.format(book=book, n=n, en=en, zh=zh, refs=REFS[subj]))

    OUT.mkdir(exist_ok=True)
    fname = f"{TODAY.isoformat()}-{subj}-{n:02d}.md"
    (OUT / fname).write_text(f"# {subj} 第{n}讲:{zh}\n\n> 教材:{book} · {en}\n\n{text}\n", encoding="utf-8")

    prog[subj] = idx + 1
    PROG.parent.mkdir(exist_ok=True)
    PROG.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")

    url = f"https://github.com/{REPO}/blob/main/lectures/{fname}"
    push(f"【{subj}】第{n}讲 {zh}", f"{extract_summary(text)}\n\n完整讲义:{url}", url)
    print("written", fname)


if __name__ == "__main__":
    main()
