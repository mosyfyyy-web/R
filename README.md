# Science News, Papers and Bookmark Sorting

An hourly GitHub Actions job that does two things.

## 1. Science news and papers
- Reads RSS feeds from NASA, ESA, Science, the Nature family, PNAS and arXiv astro-ph.
- Does nothing (and calls no LLM) when there are no new items.
- New items are scored and categorized by an LLM:
  - score 4 or higher: saved to Raindrop in a collection for its field (the collection names are in Chinese: 天文与航天, 物理与化学, 生命科学, 心理与神经, 地球与气候, 技术与工程, 其他), tagged with its type (news, paper, review, preprint) and source, with a short summary
  - score 5: also pushed to Bark
- Items whose Raindrop write failed are retried on the next run.

## 2. Auto-classification of hand-saved bookmarks
- Reads Raindrop's Unsorted collection, picks a collection and tags for each bookmark, and moves it.
- Prefers existing collections; creates at most 6 new ones per run; leaves unclear pages in Unsorted.
- Only Unsorted is touched. Bookmarks you already filed are never moved.

## Files
- `news.py`: news and paper pipeline
- `classify.py`: bookmark classifier
- `llm.py`: LLM and Bark helpers
- `.github/workflows/news.yml`: hourly schedule (minute 7)
- `state/`: de-duplication records, history, and `last_run.json` / `classify_last.json` run summaries

## Required secrets
`LLM_API_KEY`, `BARK_KEY`, `RAINDROP_TOKEN` (the Raindrop test token).
