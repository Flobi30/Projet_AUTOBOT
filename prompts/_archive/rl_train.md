# prompts/rl_train.md
## System
You are an RL trainer using Stable‑Baselines3.
## User
Write src/rl/train.py:
1. Load TradingEnv from src/rl/env.py.
2. Train PPO with CLI args (--timesteps).
3. Save model to models/ppo_trading.zip.
4. Checkpoint callback.
## Output
- src/rl/train.py
