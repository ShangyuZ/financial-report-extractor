#!/bin/bash

# -------------------------------------------------------
# Financial Extractor — Full Pipeline
# -------------------------------------------------------
# HOW TO USE:
#   1. Drop your report (.txt or .pdf) into the reports/ folder
#   2. Run this script from the financial_api/ directory: ./scripts/run.sh
#   3. Extracted JSON saved to data/{TICKER}_{FY}.json
#      Provenance artifact saved to data/{TICKER}_{FY}_data.json
# -------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load API key from .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Error: .env file not found."
    echo "Copy .env.example to .env and add your Anthropic API key."
    exit 1
fi

export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Error: ANTHROPIC_API_KEY is not set in your .env file."
    exit 1
fi

# Find the most recently added .txt or .pdf file in reports/
REPORT=$(ls -t "$PROJECT_DIR/reports/"*.txt "$PROJECT_DIR/reports/"*.pdf 2>/dev/null | head -1)
if [ -z "$REPORT" ]; then
    echo "Error: No .txt or .pdf file found in reports/"
    echo "Drop your financial report into the reports/ folder and try again."
    exit 1
fi

echo "Found report: $REPORT"
echo "Extracting financial data..."

# Any extra flags (e.g. --model claude-sonnet-4-6) are forwarded to extract.py
python3 "$PROJECT_DIR/extract.py" --file "$REPORT" --save "$@"
