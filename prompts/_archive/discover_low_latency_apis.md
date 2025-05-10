# prompts/discover_low_latency_apis.md

## System
You are a research assistant. Find low‑latency market data APIs.

## User
Write a Python script that:
1. Scrapes Google for “low latency market data API websocket”.
2. Visits top‑3 provider pages.
3. Extracts name, latency SLA, pricing URL, Python connect snippet.
4. Outputs JSON list.

## Output
- `scripts/discover_apis.py`
- Example JSON file `results/low_latency_apis.json`
