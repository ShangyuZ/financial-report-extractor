# Changelog

All notable changes to this project will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

## [0.3.0] — 2026-07-02

### Added
- FastAPI REST layer (`app/api.py`): `GET /health`, `POST /extract`, `POST /extract/compare` — exposes the extractor as an HTTP service
- `fastapi` and `uvicorn` added to `requirements.txt` (optional — only needed to run the API)

---

## [0.2.0] — 2026-06-16

### Added
- `--dry-run` flag: parse and validate input without calling the Claude API or writing files
- `CONTRIBUTING.md` with full dev setup, test, and PR instructions
- `CHANGELOG.md` (this file)

### Changed
- README badges: Python version, license, CI status

---

## [0.1.1] — 2026-06-13

### Added
- Structured logging throughout (`logging` module); `--verbose` / `--quiet` CLI flags
- Full PEP 484 type hints on every public function across all modules
- Unit test suite (`tests/test_validators.py`) — 30 tests covering all validation rules
- GitHub Actions CI (`.github/workflows/ci.yml`) — runs py_compile + pytest across Python 3.10/3.11/3.12

### Changed
- Pinned dependency versions in `requirements.txt` with inline comments

---

## [0.1.0] — 2026-06-11

### Added
- Initial release
- Multi-format input: PDF (via pypdf), plain text, image (via Claude vision)
- Structured JSON output with 25 tracked fields across income statement, balance sheet, cash flow, and guidance
- Provenance tracking: every field tagged as `extracted`, `derived`, or `missing` with source quote
- Financial logic validation: margin ranges, hierarchy checks, guidance range checks
- Two output artifacts: clean JSON + full provenance JSON
- `--batch` mode: process all files in `reports/` with a summary table
- `--compare` mode: load two extracted JSONs, print a 16-field YoY delta table
- `--output-dir` flag: override default `data/` output directory
- `--csv` flag: export flattened CSV alongside JSON
- `--model` flag: switch between `claude-haiku-4-5-20251001` (default) and `claude-sonnet-4-6`
- Single retry on JSON parse failure
