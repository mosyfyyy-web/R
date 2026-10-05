# 学习系统(长期版)

## 结构
- `study_engine.py`:引擎。四个时段:subject(学科微卡)、review(复习)、ielts(雅思)、report(周报)
- `study_data.py`:教材清单和雅思阶段目标。**新增科目、改目标都只改这个文件**
- `state/state.json`:全部进度,由 GitHub Actions 自动提交。这是唯一的数据来源,不要手动改
- `.github/workflows/study.yml`:定时任务(北京时间 08:00 / 13:00 / 21:00,周日 20:00 周报)
- `raindrop_*.py` + `raindrop.yml`:书签整理、归档、待读推送(独立运行,与学习引擎无关)

## 常见操作
- **改推送时间**:改 `study.yml` 里的 cron(UTC 时间 = 北京时间 − 8 小时)
- **新增科目**:在 `study_data.py` 的 `BOOKS` 里仿照现有格式加一项(名称、教材 slug、章节列表)
- **调整雅思阶段**:改 `study_data.py` 里的 `IELTS_MILESTONES`
- **换模型**:仓库 Settings → Secrets and variables → Actions → Variables,改 `LLM_BASE_URL` 和 `LLM_MODEL`
- **手动预览**:Actions → study → Run workflow,选 slot,不勾 apply

## 出问题时
- 手机收到「学习系统出错了」:打开 Actions 页面看最近一次失败的日志
- 连续几天没收到推送:先看 Actions 里定时任务是不是被停用了(公开仓库 60 天无任何活动会被 GitHub 暂停,点 Enable 即可;系统每天提交进度,正常情况下不会触发)
- 进度丢了:`state/state.json` 在 git 历史里,可以回滚到任意一天

## 已知限制
- 微卡由免费模型生成,以教材原文为准
- 目前是单向推送,系统不知道你答对没有,复习间隔是固定的(1/4/14/45 天)。有了网页端后可以按你的作答自适应
