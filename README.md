# 科学快讯与论文推送

每小时检查 NASA、ESA、Science、Nature 系列、PNAS、arXiv 天体物理的 RSS。
有新条目才调用 LLM 打分和分类:
- 3 分以上:自动存入 Raindrop 对应分类收藏夹(天文与航天、物理与化学、生命科学、心理与神经、地球与气候、技术与工程、其他)
- 4 分以上:同时推送到 Bark

文件:`news.py`(主程序)、`llm.py`(LLM 与 Bark)、`.github/workflows/news.yml`(定时任务)、
`state/`(去重记录、历史、`last_run.json` 运行状态)。

所需 Secrets:`LLM_API_KEY`、`BARK_KEY`、`RAINDROP_TOKEN`。
