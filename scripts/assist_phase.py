# File: scripts/assist_phase.py
"""
Orchestrator pour assister le développement du projet AUTOBOT
via l'API OpenAI (gpt-4o-mini), avec suivi d'état,
idempotence, et intégration des prompts depuis prompts/archive/.
"""
import os
import json
import argparse
from pathlib import Path
from openai import OpenAI

# --- Configuration OpenAI ---
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("Veuillez définir la variable d'environnement OPENAI_API_KEY.")
client = OpenAI(api_key=API_KEY)

# --- Fichiers et répertoires ---
STATE_FILE = Path(".assistant_state.json")
PROMPT_DIR = Path("prompts/archive")

# --- Gestion d'état ---
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"completed": []}

def save_state(state: dict):
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )

def already_done(task: str, state: dict) -> bool:
    return task in state.get("completed", [])

def mark_done(task: str, state: dict):
    state.setdefault("completed", []).append(task)
    save_state(state)
    print(f"✅ Tâche '{task}' marquée comme réalisée.")

# --- Chargement du prompt ---
def load_prompt(task_key: str, default_prompt: str) -> str:
    """
    Charge le prompt depuis prompts/archive/{task_key}.md si disponible,
    sinon retourne default_prompt.
    """
    md_file = PROMPT_DIR / f"{task_key}.md"
    if md_file.exists():
        print(f"📥 Chargé prompt archive pour '{task_key}'")
        return md_file.read_text(encoding="utf-8")
    print(f"📥 Utilisation du prompt par défaut pour '{task_key}'")
    return default_prompt

# --- Définition des tâches ---
TASKS = {
    # Generation & infra
    "add_fastapi_predict": {
        "path": Path("src/autobot/main.py"),
        "default_prompt": (
            "Ajoute un endpoint FastAPI GET /predict dans src/autobot/main.py qui retourne {'prediction': 0.5}"
        )
    },
    "update_dockerfile": {
        "path": Path("Dockerfile"),
        "default_prompt": (
            "Met à jour le Dockerfile pour installer prod et dev deps, exposer 8000 et lancer Uvicorn"
        )
    },
    "ci_cd_pipeline": {
        "path": Path(".github/workflows/ci-cd.yml"),
        "default_prompt": (
            "Crée un workflow GitHub Actions pour tester, build Docker, push image et déployer sur Kubernetes"
        )
    },
    # Business endpoints
    "add_backtest_endpoint": {
        "path": Path("src/autobot/router.py"),
        "default_prompt": (
            "Dans src/autobot/router.py, ajoute POST /backtest avec schéma Pydantic BacktestRequest et BacktestResult, metrics simulées."
        )
    },
    "add_metrics_endpoint": {
        "path": Path("src/autobot/router.py"),
        "default_prompt": (
            "Dans src/autobot/router.py, ajoute GET /metrics renvoyant un dict JSON de KPI e-commerce factices."
        )
    },
    "add_train_endpoint": {
        "path": Path("src/autobot/router.py"),
        "default_prompt": (
            "Dans src/autobot/router.py, ajoute POST /train qui démarre l'entraînement RL et retourne job_id simulé."
        )
    },
    "add_logs_endpoint": {
        "path": Path("src/autobot/router.py"),
        "default_prompt": (
            "Dans src/autobot/router.py, ajoute GET /logs qui renvoie la liste des logs JSON via autobot_guardian."
        )
    },
    # Tests endpoints
    "add_test_backtest": {
        "path": Path("tests/test_backtest_endpoint.py"),
        "default_prompt": (
            "Crée un test Pytest pour POST /backtest vérifiant 200, présence de strategy et metrics."
        )
    },
    "add_test_metrics": {
        "path": Path("tests/test_metrics_endpoint.py"),
        "default_prompt": (
            "Crée un test Pytest pour GET /metrics vérifiant 200 et format JSON."
        )
    },
    "add_test_train": {
        "path": Path("tests/test_train_endpoint.py"),
        "default_prompt": (
            "Crée un test Pytest pour POST /train vérifiant 200 et champ job_id."
        )
    },
    "add_test_logs": {
        "path": Path("tests/test_logs_endpoint.py"),
        "default_prompt": (
            "Crée un test Pytest pour GET /logs vérifiant 200 et liste JSON."
        )
    },
    # AI plugins
    "add_ai_signals_plugin": {
        "path": Path("src/autobot/plugins/ai_signals.py"),
        "default_prompt": (
            "Crée src/autobot/plugins/ai_signals.py avec fonction get_signals() appelant une URL fictive REST."
        )
    },
    "add_capital_companion_plugin": {
        "path": Path("src/autobot/plugins/capital_companion.py"),
        "default_prompt": (
            "Crée src/autobot/plugins/capital_companion.py avec get_recommendations() vers API Capital Companion."
        )
    },
    "add_quantum_ai_plugin": {
        "path": Path("src/autobot/plugins/quantum_ai.py"),
        "default_prompt": (
            "Crée src/autobot/plugins/quantum_ai.py avec execute_quantum_strategy()."
        )
    },
    "add_mettalex_plugin": {
        "path": Path("src/autobot/plugins/mettalex.py"),
        "default_prompt": (
            "Crée src/autobot/plugins/mettalex.py pour arbitrage cross-chain."
        )
    },
    "add_sentiment_agent_plugin": {
        "path": Path("src/autobot/plugins/sentiment_agent.py"),
        "default_prompt": (
            "Crée src/autobot/plugins/sentiment_agent.py scrappant Twitter/RSS pour sentiment."
        )
    },
    # Deployment scripts
    "docker_build": {
        "path": Path("scripts/deploy.sh"),
        "default_prompt": (
            "Crée scripts/deploy.sh pour build Docker, tag ${GITHUB_SHA}, push registry."
        )
    },
    "k8s_deploy": {
        "path": Path("scripts/deploy_k8s.sh"),
        "default_prompt": (
            "Crée scripts/deploy_k8s.sh pour kubectl set image et rollout status."
        )
    },
    "add_real_backtest_engine": {
        "path": Path("src/autobot/backtest_engine.py"),
        "default_prompt": "Dans src/autobot/backtest_engine.py : Crée une fonction run_backtest(strategy_name: str, parameters: dict) -> dict, modifie POST /backtest dans router pour utiliser run_backtest, ajoute # REAL_BACKTEST"
    },
    "add_rl_training_integration": {
        "path": Path("src/autobot/rl/train.py"),
        "default_prompt": "Dans src/autobot/rl/train.py : Expose start_training() qui lance RLModule.train(), retourne job_id, modifie POST /train pour utiliser start_training, ajoute # REAL_RL_TRAIN"
    },
    "add_ecommerce_metrics_integration": {
        "path": Path("src/autobot/ecommerce/kpis.py"),
        "default_prompt": "Dans src/autobot/ecommerce/kpis.py : Assure get_kpis(), modifie GET /metrics dans router pour utiliser get_kpis(), ajoute # REAL_ECOM_KPIS"
    },
    "add_monitoring_integration": {
        "path": Path("src/autobot/guardian.py"),
        "default_prompt": "Dans src/autobot/guardian.py : Ajoute get_metrics() pour CPU/mémoire/latence, crée endpoint GET /monitoring dans router, ajoute # REAL_MONITORING"
    },
    "add_live_trade_endpoint": {
        "path": Path("src/autobot/router.py"),
        "default_prompt": "Dans src/autobot/router.py : Ajoute POST /trade pour placer un ordre, importe execute_trade(), crée src/autobot/trading.py, ajoute # REAL_TRADE"
    },
    "add_risk_manager": {
        "path": Path("src/autobot/risk_manager.py"),
        "default_prompt": "Crée src/autobot/risk_manager.py avec calculate_position_size(), modifie execute_trade pour utiliser calculate_position_size(), ajoute # REAL_RISK"
    },
}

# --- Helpers ---
def ensure_file(path: Path):
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")

# --- Core functions ---
def generate_with_openai(prompt: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Vous êtes un assistant de code précis."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    return resp.choices[0].message.content


def apply_patch(path: Path, content: str):
    path.write_text(content, encoding="utf-8")
    print(f"🔧 Fichier mis à jour : {path}")


def perform_task(task_key: str, state: dict):
    if task_key not in TASKS:
        print(f"⚠️ Tâche inconnue : {task_key}")
        return
    if already_done(task_key, state):
        print(f"⚠️ Tâche '{task_key}' déjà effectuée → skip complet.")
        return
    default = TASKS[task_key]["default_prompt"]
    prompt = load_prompt(task_key, default)
    cfg = TASKS[task_key]
    fp = cfg["path"]
    ensure_file(fp)
    print(f"🔄 Génération de code pour '{task_key}'…")
    new_code = generate_with_openai(prompt)
    print(f"🔧 Application du code généré sur {fp}…")
    apply_patch(fp, new_code)
    mark_done(task_key, state)


def perform_all():
    state = load_state()
    for key in TASKS.keys():
        perform_task(key, state)

# --- CLI ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Assistant code AUTOBOT avec suivi d'état et prompts archive"
    )
    parser.add_argument(
        "task",
        choices=list(TASKS.keys()) + ["all"],
        help="Nom de la tâche à exécuter ou 'all' pour tout faire"
    )
    args = parser.parse_args()
    state = load_state()
    if args.task == "all":
        perform_all()
    else:
        perform_task(args.task, state)
