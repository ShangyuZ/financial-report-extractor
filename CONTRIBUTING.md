# Contributing

## Development Setup

```bash
git clone https://github.com/ShangyuZ/financial-report-extractor.git
cd financial-report-extractor/financial_api

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env             # add your ANTHROPIC_API_KEY
```

## Running Tests

```bash
cd financial_api
python -m pytest tests/ -v
```

## Running the Extractor

```bash
# single file
python extract.py --file reports/your_report.pdf --save

# batch (all files in reports/)
python extract.py --batch --save

# dry run — preview without API call
python extract.py --file reports/your_report.pdf --dry-run

# compare two extracted JSONs
python extract.py --compare data/TICKER_FY2023.json data/TICKER_FY2024.json
```

## Code Style

- Python 3.10+
- Type hints on all public functions
- Docstrings for all public functions (Google style)
- Specific exception types — no bare `except:`
- Keep `max_tokens` ≤ 2500 to control API costs

## Submitting Changes

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Run tests: `python -m pytest tests/ -v`
4. Open a PR with a clear description of what changed and why
