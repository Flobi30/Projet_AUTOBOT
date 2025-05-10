# prompts/agents_adapter.md

## System
You are an integration engineer. Generate adapters for IA agents.

## User
For each agent:
- Name: SentimentAI, API: https://api.sentimentai.com/v1/analyze, Auth: Bearer token.
- Name: MacroML, Python SDK `pip install macroml`.

Generate:
1. `class SentimentAIAdapter` with `analyze(text: str) -> dict`.
2. `class MacroMLAdapter` with `get_indicators(symbol: str, start: date, end: date) -> DataFrame`.
3. Register them in `agents/registry.py`.

## Output
- `src/agents/adapters.py`
- `src/agents/registry.py`
- Tests in `tests/test_agents.py`
