#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import typer
from generate_full_project import generate_full_project
from generate_ai_agents import generate_ai_agents
from generate_utils import generate_utils
from generate_autobot_guardian import generate_autobot_guardian
import autoupdate.hpo as hpo_module

app = typer.Typer()

@app.command()
def init():
    """Bootstrap complet: structure, modules, agents, utils, guardian."""
    generate_full_project()
    generate_ai_agents()
    generate_utils()
    generate_autobot_guardian()
    typer.secho("✅ Bootstrap généré.", fg=typer.colors.GREEN)

@app.command()
def hpo():
    """Lance l'HPO via Ray Tune."""
    typer.secho("🚀 Démarrage HPO...", fg=typer.colors.BLUE)
    hpo_module.main()

if __name__ == '__main__':
    app()

