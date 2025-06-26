"""
LAUNCH_MASTER_PLAN (SAFE VERSION)
Lance automatiquement Open Interpreter et exécute le contenu de `autobot_master_plan.md`
sans interaction manuelle. Compatible Windows sans emojis.
"""

import subprocess
import time

PLAN_PATH = "prompts/_archive/autobot_master_plan.md"

def read_plan():
    with open(PLAN_PATH, "r", encoding="utf-8") as f:
        return f.read()

def launch_open_interpreter():
    try:
        print("Démarrage de Open Interpreter avec injection du contenu...")
        content = read_plan()

        process = subprocess.Popen(
            ["interpreter"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        commands = [
            f'content = """{content}"""',
            "exec(content)",
        ]

        for cmd in commands:
            print(f">> {cmd}")
            process.stdin.write(cmd + "\n")
            time.sleep(1)

        process.stdin.write("y\n" * 50)
        process.stdin.flush()

        print("Contenu injecté. Exécution en cours...")
        process.communicate(timeout=None)

    except Exception as e:
        print("Erreur :", e)

if __name__ == "__main__":
    launch_open_interpreter()

