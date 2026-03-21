# Financial Report Extractor

Turn raw financial reports into clean, validated, machine-readable JSON, powered by Claude AI.

---

## The Problem

Financial reports (earnings releases, annual reports, investor documents) are written for humans. They're dense, inconsistent, and unstructured. Extracting the numbers reliably is fragile and time-consuming.

## What This Does

Drop a financial report into the `reports/` folder and run one command. The extractor reads the document, pulls out every key financial metric (revenue, EBITDA, cash flow, balance sheet, segments, guidance), validates the output for logical consistency, and saves two JSON files: a clean structured output and a full provenance record showing exactly where each number came from.

## How It Works

```
Input report (.pdf / .txt / .png / .jpg)
               ↓
     Claude extracts financials
               ↓
     Pydantic schema validation
               ↓
     Financial logic checks
               ↓
  Clean JSON  +  Provenance record
```

## Key Features

- **Multi-format input:** PDF, plain text, or image
- **Structured output:** income statement, balance sheet, cash flow, YoY changes, segments, guidance
- **Provenance tracking:** every field tagged as `extracted`, `derived`, or `missing`, with a source quote from the document
- **Financial validation:** logical sanity checks including margin consistency, hierarchy, and guidance ranges
- **Two output artifacts:** a clean JSON for downstream use and a full provenance JSON for auditing
- **Coverage summary:** terminal output shows how many fields were extracted, derived, or missing

## Quick Start

```bash
cd financial_api
pip install -r requirements.txt
cp .env.example .env          # paste your Anthropic API key
# drop your report into reports/
./scripts/run.sh
```

Output is saved to `financial_api/data/`.

---

For architecture, CLI reference, output format, and pipeline details, see the [technical README](financial_api/README.md).
