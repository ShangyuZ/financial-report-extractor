# Financial Report Extractor: Technical Reference

## Architecture

```
financial_api/
├── app/
│   ├── extractor.py       Claude API call, prompt, response parsing, retry logic
│   ├── models.py          Pydantic schema for all financial data models
│   └── validators.py      Financial logic checks (margins, hierarchy, guidance)
├── scripts/
│   └── run.sh             Shell entry point
├── examples/              Sample input reports
├── sample_outputs/        Example extraction outputs
├── reports/               Drop your input files here (gitignored)
├── data/                  Generated output (gitignored)
├── extract.py             CLI for argument parsing, orchestration, and file I/O
├── requirements.txt
└── .env.example
```

---

## Pipeline

**1. Input detection:** `extract.py` inspects the file extension:
- `.pdf` → text extracted page-by-page via `pypdf`, then passed as text
- `.png` / `.jpg` / `.jpeg` → encoded as base64 and sent to Claude's vision API
- `.txt` → passed as-is

**2. Extraction:** `extractor.py` sends the report to Claude with a structured prompt at `temperature=0`. Claude returns a single JSON object with three keys: `financials`, `metadata`, and `extraction_warnings`. A single retry is attempted if the response fails to parse.

**3. Schema validation:** The `financials` block is validated against Pydantic models in `models.py`. Two derived fields are computed automatically if their components are present:
- `net_debt = total_debt − cash_and_equivalents`
- `free_cash_flow = operating_cash_flow − capex`

**4. Financial validation:** `validators.py` runs logical sanity checks:
- Revenue ≥ gross profit (error if violated)
- Margin range 0–100% (warning if outside)
- Stated margins vs. computed margins, 1pp tolerance (warning if they diverge)
- Guidance low ≤ high (error if inverted)

**5. Output:** Two files written to `data/`:
- `{TICKER}_{FY}.json`: clean financials only
- `{TICKER}_{FY}_data.json`: full provenance record

---

## CLI Usage

```bash
# Shell script (recommended, auto-picks latest file in reports/)
./scripts/run.sh

# Text file
python3 extract.py --file reports/report.txt --save

# PDF
python3 extract.py --file reports/report.pdf --save

# Image
python3 extract.py --file reports/report.png --save

# Inline text
python3 extract.py --text "Revenue $1.2bn, net income $180M, FY2024, Ticker: ACME" --save

# Higher accuracy model
python3 extract.py --file reports/report.pdf --save --model claude-sonnet-4-6
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--file PATH` | none | Path to a `.txt`, `.pdf`, `.png`, or `.jpg` report |
| `--text TEXT` | none | Inline report text (alternative to `--file`) |
| `--save` | off | Write output files to `data/` |
| `--model MODEL` | `claude-haiku-4-5-20251001` | Claude model to use |

---

## Output Files

### `{TICKER}_{FY}.json`: Clean Financials

Structured data ready for downstream use. Contains:

```json
{
  "company": { "name", "ticker", "sector", "fiscal_year", "currency", "period" },
  "income_statement": { "revenue", "gross_profit", "ebitda", "ebit", "net_income",
                        "eps_diluted", "gross_margin", "ebitda_margin", "net_margin" },
  "balance_sheet": { "total_assets", "total_debt", "cash_and_equivalents",
                     "net_debt", "total_equity", "working_capital" },
  "cash_flow": { "operating_cash_flow", "capex", "free_cash_flow", "dividends_paid" },
  "yoy_changes": { "revenue", "ebitda", "net_income", "eps_diluted" },
  "segments": [ { "name", "revenue", "operating_income", "revenue_growth_yoy" } ],
  "guidance": { "revenue_low", "revenue_high", "ebitda_low", "ebitda_high",
                "eps_low", "eps_high", "commentary" }
}
```

All monetary values are in **millions USD**. Percentages are plain numbers (8.2%, not 0.082).

### `{TICKER}_{FY}_data.json`: Provenance Record

Full audit artifact. Contains `financials` (same as above) plus:

- `metadata`: per-field provenance (see below)
- `extraction_warnings`: conflicts or ambiguities flagged during extraction
- `validation_warnings`: advisory checks (unusual but not blocking)
- `validation_errors`: blocking issues that caused extraction to fail

---

## Metadata and Trust Layer

Every tracked field in the provenance record has three attributes:

```json
"income_statement.revenue": {
  "source": "Total Revenue (USD M) $1,284.5",
  "status": "extracted",
  "reason": null
}
```

| Attribute | Values | Meaning |
|-----------|--------|---------|
| `source` | quoted phrase or `null` | Shortest phrase from the document that supports the value |
| `status` | `extracted` / `derived` / `missing` | How the value was obtained |
| `reason` | string or `null` | Explanation when `status` is `missing` |

**Tracked fields (25 total):**
- 3 company identity: `company.name`, `company.ticker`, `company.fiscal_year`
- 9 income statement fields
- 5 balance sheet fields
- 4 cash flow fields
- 4 guidance fields: `guidance.revenue_low/high`, `guidance.eps_low/high`

---

## Terminal Output

```
Extraction complete: 24 extracted, 1 derived, 0 missing
```

Warnings and errors print to stderr with `[WARN]` / `[ERROR]` / `[EXTRACT]` prefixes. Clean JSON prints to stdout.

---

## Notes

- Claude is called at `temperature=0` for deterministic output
- `max_tokens=2500`: if truncation occurs, use a shorter input or split the document
- Default model is `claude-haiku-4-5-20251001` (cost-efficient); use `--model claude-sonnet-4-6` for higher accuracy on complex documents
- See `examples/` for a sample input report and `sample_outputs/` for the corresponding extraction results
