#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '/home/ubuntu/Projet_AUTOBOT/src')

from autobot.main import app
import uvicorn

if __name__ == "__main__":
    print("Starting AUTOBOT server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
