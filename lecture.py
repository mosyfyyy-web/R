"""每日讲义:按 study_data.BOOKS 的章节顺序,每次生成一章,讲稿全文直接推送到 Bark(不存仓库)。
只在仓库里保存进度数字。天文学与心理学隔天交替。"""
import sys, json, datetime as dt
from pathlib import Path
from study_data import BOOKS
from llm import ask, push_long, KEY

TODAY = dt.date.today()
PROG = Path("state/lecture_progress.json")

REFS = {
    "天文学": "Chaisson 和 McMillan 的《Astronomy Today》(Pearson)、Carroll 和 Ostlie 的《An Introduction to Modern Astrophysics》",
    "心理学": "Gerrig 和 Zimbardo 的《Psychology and Life》(Pearson)、Myers 的《Psychology》",
}

PROMPT = """你是一位讲课很好的大学教授,现在对一位学习者做一次当面授课。内容是 OpenStax《{book}》第 {n} 章「{en}」(中文:{zh})。

写成你亲口讲出来的讲稿,要求:
- 纯文本,像说话一样连贯。不要标题、不要编号、不要项目符号、不要加粗、不要 Markdown、不要 LaTeX。公式直接用文字写,例如 P平方 = a立方。
- 不要套话。不要写"本讲""同学们""首先其次最后""总之""综上所述""值得注意的是"这类词。直接从一个具体的问题或现象切入。
- 专业水平。讲清楚原理、推导思路和数量级,用具体数字和具体例子,遇到常见的错误理解要当场点破,并讲明白错在哪。
- 用你自己的话讲,不要照搬任何教材原文。
- 只在最后用一两句话自然地提一下:这个主题在{refs}里对应讲哪方面,可以拿来对照。不要编造页码或章节号。
- 全文 2200 到 2800 个汉字,分 5 到 8 个自然段,段与段之间空一行。
"""


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
    push_long(f"【{subj}】第{n}章 {zh}", text, "", group="讲义")

    prog[subj] = idx + 1
    PROG.parent.mkdir(exist_ok=True)
    PROG.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
    print("pushed", subj, n)


if __name__ == "__main__":
    main()
