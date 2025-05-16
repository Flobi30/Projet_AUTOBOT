#!/bin/bash

echo "🧹 Starting project cleanup..."

echo "Removing Python compiled files..."
find . -name "__pycache__" -type d -exec rm -rf {} \; 2>/dev/null || true
find . -name "*.pyc" -delete
find . -name "*.pyo" -delete
find . -name "*.pyd" -delete

echo "Removing build and distribution directories..."
find . -name "build" -type d -exec rm -rf {} \; 2>/dev/null || true
find . -name "dist" -type d -exec rm -rf {} \; 2>/dev/null || true
find . -name "*.egg-info" -type d -exec rm -rf {} \; 2>/dev/null || true

echo "Removing virtual environments..."
find . -name "venv" -type d -exec rm -rf {} \; 2>/dev/null || true
find . -name "ENV" -type d -exec rm -rf {} \; 2>/dev/null || true

echo "Removing logs and temporary data..."
find . -name "logs" -type d -exec rm -rf {} \; 2>/dev/null || true
find . -name "*.log" -delete
find . -name "data" -type d -exec rm -rf {} \; 2>/dev/null || true

echo "✅ Cleanup completed!"
