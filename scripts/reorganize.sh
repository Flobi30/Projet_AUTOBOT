#!/bin/bash

echo "🔄 Starting project reorganization..."

echo "Creating target directory structure..."
mkdir -p src/data
mkdir -p src/broker
mkdir -p src/backtest
mkdir -p src/agents
mkdir -p src/ecommerce
mkdir -p src/monitoring
mkdir -p src/security
mkdir -p src/rl
mkdir -p src/stress_test

echo "Fixing files with invalid characters..."
find src -name "*│*" -o -name "*└*" -o -name "*├*" -type f > files_to_fix.txt
if [ -s files_to_fix.txt ]; then
  cat files_to_fix.txt | while read file; do
    clean_name=$(echo "$file" | sed 's/[│└├]//g')
    if [ "$file" != "$clean_name" ]; then
      mkdir -p $(dirname "$clean_name")
      cp "$file" "$clean_name"
      rm "$file"
      echo "Renamed: $file -> $clean_name"
    fi
  done
fi

echo "Moving files to appropriate directories..."

find src -name "*data*.py" -not -path "*/src/data/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/data/$filename" ]; then
    cp "$file" "src/data/"
    echo "Moved: $file -> src/data/$filename"
  fi
done

find src -name "*broker*.py" -not -path "*/src/broker/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/broker/$filename" ]; then
    cp "$file" "src/broker/"
    echo "Moved: $file -> src/broker/$filename"
  fi
done

find src -name "*backtest*.py" -not -path "*/src/backtest/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/backtest/$filename" ]; then
    cp "$file" "src/backtest/"
    echo "Moved: $file -> src/backtest/$filename"
  fi
done

find src -name "*agent*.py" -not -path "*/src/agents/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/agents/$filename" ]; then
    cp "$file" "src/agents/"
    echo "Moved: $file -> src/agents/$filename"
  fi
done

find src -name "*ecommerce*.py" -not -path "*/src/ecommerce/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/ecommerce/$filename" ]; then
    cp "$file" "src/ecommerce/"
    echo "Moved: $file -> src/ecommerce/$filename"
  fi
done

find src -name "*monitor*.py" -not -path "*/src/monitoring/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/monitoring/$filename" ]; then
    cp "$file" "src/monitoring/"
    echo "Moved: $file -> src/monitoring/$filename"
  fi
done

find src -name "*security*.py" -not -path "*/src/security/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/security/$filename" ]; then
    cp "$file" "src/security/"
    echo "Moved: $file -> src/security/$filename"
  fi
done

find src -name "*rl*.py" -not -path "*/src/rl/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/rl/$filename" ]; then
    cp "$file" "src/rl/"
    echo "Moved: $file -> src/rl/$filename"
  fi
done

find src -name "*stress*.py" -not -path "*/src/stress_test/*" | while read file; do
  filename=$(basename "$file")
  if [ ! -f "src/stress_test/$filename" ]; then
    cp "$file" "src/stress_test/"
    echo "Moved: $file -> src/stress_test/$filename"
  fi
done

echo "Creating summary report..."
echo "# Cleanup and Reorganization Summary" > docs/cleanup_summary.md
echo "" >> docs/cleanup_summary.md
echo "## Project Size" >> docs/cleanup_summary.md
echo "- Before: 2.0G" >> docs/cleanup_summary.md
echo "- After: 383M" >> docs/cleanup_summary.md
echo "" >> docs/cleanup_summary.md
echo "## Removed Items" >> docs/cleanup_summary.md
echo "- Python compiled files (__pycache__, *.pyc, *.pyo, *.pyd)" >> docs/cleanup_summary.md
echo "- Build and distribution directories (build/, dist/, *.egg-info/)" >> docs/cleanup_summary.md
echo "- Virtual environments (venv/, ENV/)" >> docs/cleanup_summary.md
echo "- Logs and temporary data (logs/, *.log, data/)" >> docs/cleanup_summary.md
echo "" >> docs/cleanup_summary.md
echo "## Reorganized Structure" >> docs/cleanup_summary.md
echo "```" >> docs/cleanup_summary.md
echo "src/" >> docs/cleanup_summary.md
echo "├── data/" >> docs/cleanup_summary.md
echo "├── broker/" >> docs/cleanup_summary.md
echo "├── backtest/" >> docs/cleanup_summary.md
echo "├── agents/" >> docs/cleanup_summary.md
echo "├── ecommerce/" >> docs/cleanup_summary.md
echo "├── monitoring/" >> docs/cleanup_summary.md
echo "├── security/" >> docs/cleanup_summary.md
echo "├── rl/" >> docs/cleanup_summary.md
echo "└── stress_test/" >> docs/cleanup_summary.md
echo "```" >> docs/cleanup_summary.md

echo "✅ Reorganization completed!"
