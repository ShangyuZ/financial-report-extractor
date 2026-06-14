#!/usr/bin/env python3
"""
extract.py — CLI tool: raw report → structured financial JSON

Supported input formats:
  --file report.txt          Plain text
  --file report.pdf          PDF (text extracted automatically via pypdf)
  --file report.png          Image — PNG, JPG, JPEG (sent to Claude vision API)
  --text "Revenue was ..."   Inline text string

Additional modes:
  --batch                    Process every file in reports/ and print a summary table
  --compare A.json B.json    Load two extracted JSONs and print a YoY delta table

Verbosity:
  --verbose                  Enable DEBUG-level logging
  --quiet                    Suppress all stderr output except errors
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import sys
from pathlib import Path

# Load .env if present
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Allow running from the financial-api directory without installing the package
sys.path.insert(0, str(Path(__file__).parent))

from app.extractor import extract, extract_from_image, EXPECTED_METADATA_KEYS, VALID_STATUSES
from app.validators import validate_financial_data

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES: frozenset[str] = frozenset({".png", ".jpg", ".jpeg"})
_PDF_SUFFIX: str = ".pdf"
_SUPPORTED_SUFFIXES: frozenset[str] = _IMAGE_SUFFIXES | frozenset({_PDF_SUFFIX, ".txt"})


def _configure_logging(verbose: bool, quiet: bool) -> None:
    """Configure root logger based on verbosity flags.

    Args:
        verbose: If True, set level to DEBUG.
        quiet:   If True, set level to ERROR (suppress INFO/WARNING).
    """
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        level = logging.WARNING

    logging.basicConfig(
        format="%(levelname)s %(name)s: %(message)s",
        level=level,
        stream=sys.stderr,
    )


def _pdf_to_text(path: Path) -> str:
    """Extract text from a PDF file using pypdf.

    Args:
        path: Path to the PDF file.

    Returns:
        Concatenated text from all pages, joined by double newlines.

    Raises:
        SystemExit: If pypdf is not installed.
    """
    try:
        import pypdf
    except ImportError:
        print("Error: pypdf is required for PDF support. Install with: pip install pypdf", file=sys.stderr)
        sys.exit(1)
    reader = pypdf.PdfReader(str(path))
    pages: list[str] = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _run_extraction(
    path: Path, model: str
) -> tuple[dict, list[str], list[str], list[str]]:
    """Extract financials from a single file.

    Args:
        path:  Path to the input file (.txt, .pdf, .png, .jpg, .jpeg).
        model: Claude model identifier.

    Returns:
        A 4-tuple of ``(financials_dict, extraction_warnings, validation_warnings, validation_errors)``.
    """
    suffix = path.suffix.lower()
    is_image = suffix in _IMAGE_SUFFIXES

    if suffix == _PDF_SUFFIX:
        logger.info("Detected PDF — extracting text: %s", path.name)
        text: str | None = _pdf_to_text(path)
    elif is_image:
        text = None
    else:
        text = path.read_text(encoding="utf-8")

    if is_image:
        logger.info("Detected image — sending to Claude vision: %s", path.name)
        result = extract_from_image(str(path), model=model)
    else:
        assert text is not None
        result = extract(text, model=model)

    data = result.financials
    val_warnings, val_errors = validate_financial_data(data)
    return data, result.extraction_warnings, val_warnings, val_errors


def _save_outputs(
    data: dict,
    result_extraction_warnings: list[str],
    val_warnings: list[str],
    val_errors: list[str],
    out_dir: Path,
    export_csv: bool,
) -> tuple[Path, Path]:
    """Write JSON (and optionally CSV) outputs to disk.

    Args:
        data:                       Validated financials dict.
        result_extraction_warnings: Warnings raised by the Claude extraction step.
        val_warnings:               Advisory warnings from the validator.
        val_errors:                 Blocking errors from the validator.
        out_dir:                    Target directory (created if absent).
        export_csv:                 If True, also write a flattened CSV.

    Returns:
        A ``(json_path, artifact_path)`` tuple of the written files.
    """
    ticker: str = (data.get("company") or {}).get("ticker") or "UNKNOWN"
    fy: str = (data.get("company") or {}).get("fiscal_year") or "UNKNOWN"
    out_dir.mkdir(parents=True, exist_ok=True)

    output_json = json.dumps(data, indent=2)

    json_path = out_dir / f"{ticker}_{fy}.json"
    json_path.write_text(output_json, encoding="utf-8")

    artifact: dict = {
        "financials": data,
        "extraction_warnings": result_extraction_warnings,
        "validation_warnings": val_warnings,
        "validation_errors": val_errors,
    }
    artifact_path = out_dir / f"{ticker}_{fy}_data.json"
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    if export_csv:
        csv_path = out_dir / f"{ticker}_{fy}.csv"
        _write_csv(data, csv_path)
        logger.info("CSV written: %s", csv_path)

    return json_path, artifact_path


def _write_csv(data: dict, path: Path) -> None:
    """Flatten the financials dict to a two-column CSV (field, value).

    Args:
        data: The financials dict to flatten.
        path: Destination file path.
    """
    rows: list[tuple[str, object]] = []

    def _flatten(obj: object, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flatten(v, f"{prefix}{k}.")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _flatten(item, f"{prefix}[{i}].")
        else:
            rows.append((prefix.rstrip("."), obj))

    _flatten(data)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["field", "value"])
    writer.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


def _print_coverage(metadata: dict) -> None:
    """Print a concise field-coverage summary to stderr.

    Args:
        metadata: The metadata dict from an :class:`ExtractionResult`.
    """
    counts: dict[str, int] = {"extracted": 0, "derived": 0, "missing": 0}
    for key in EXPECTED_METADATA_KEYS:
        status = (metadata.get(key) or {}).get("status")
        if status in counts:
            counts[status] += 1
    print(
        f"  Coverage: {counts['extracted']} extracted, "
        f"{counts['derived']} derived, {counts['missing']} missing",
        file=sys.stderr,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Batch mode
# ──────────────────────────────────────────────────────────────────────────────

def _batch(reports_dir: Path, out_dir: Path, model: str, export_csv: bool) -> None:
    """Process all supported files in ``reports_dir`` and print a summary table.

    Args:
        reports_dir: Directory to scan for supported input files.
        out_dir:     Directory where output files are written.
        model:       Claude model identifier.
        export_csv:  If True, also write a flattened CSV per file.
    """
    files: list[Path] = sorted(
        p for p in reports_dir.iterdir()
        if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES
    )
    if not files:
        print(f"No supported files found in {reports_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Batch mode: {len(files)} file(s) found in {reports_dir}\n", file=sys.stderr)

    summary: list[dict] = []

    for f in files:
        print(f"Processing: {f.name}", file=sys.stderr)
        try:
            data, ext_warnings, val_warnings, val_errors = _run_extraction(f, model)
            co: dict = data.get("company") or {}
            inc: dict = data.get("income_statement") or {}
            row: dict = {
                "file": f.name,
                "company": co.get("name") or "—",
                "ticker": co.get("ticker") or "—",
                "period": co.get("period") or co.get("fiscal_year") or "—",
                "revenue": inc.get("revenue"),
                "ebitda_margin": inc.get("ebitda_margin"),
                "net_income": inc.get("income_statement", {}).get("net_income") or inc.get("net_income"),
                "status": "OK" if not val_errors else f"ERR({len(val_errors)})",
                "warnings": len(val_warnings) + len(ext_warnings),
            }
            summary.append(row)
            _save_outputs(data, ext_warnings, val_warnings, val_errors, out_dir, export_csv)
            print(f"  Saved to {out_dir}", file=sys.stderr)
        except (ValueError, OSError) as e:
            summary.append({"file": f.name, "company": "—", "ticker": "—", "period": "—",
                             "revenue": None, "ebitda_margin": None, "net_income": None,
                             "status": "FAIL", "warnings": 0})
            print(f"  Failed: {e}", file=sys.stderr)
            logger.exception("Batch extraction failed for %s", f.name)
        print("", file=sys.stderr)

    # Print summary table
    col_w: dict[str, int] = {
        "file": 30, "company": 22, "ticker": 8, "period": 10,
        "revenue": 12, "ebitda_margin": 14, "status": 12, "warnings": 8,
    }

    def _cell(v: object, w: int) -> str:
        s = "—" if v is None else (f"{v:,.1f}" if isinstance(v, float) else str(v))
        return s[:w].ljust(w)

    header = (
        _cell("File", col_w["file"]) +
        _cell("Company", col_w["company"]) +
        _cell("Ticker", col_w["ticker"]) +
        _cell("Period", col_w["period"]) +
        _cell("Revenue (M)", col_w["revenue"]) +
        _cell("EBITDA Margin%", col_w["ebitda_margin"]) +
        _cell("Status", col_w["status"]) +
        _cell("Warns", col_w["warnings"])
    )
    sep = "-" * len(header)
    print("\nBatch Summary")
    print(sep)
    print(header)
    print(sep)
    for row in summary:
        print(
            _cell(row["file"], col_w["file"]) +
            _cell(row["company"], col_w["company"]) +
            _cell(row["ticker"], col_w["ticker"]) +
            _cell(row["period"], col_w["period"]) +
            _cell(row["revenue"], col_w["revenue"]) +
            _cell(row["ebitda_margin"], col_w["ebitda_margin"]) +
            _cell(row["status"], col_w["status"]) +
            _cell(row["warnings"], col_w["warnings"])
        )
    print(sep)
    ok_count = sum(1 for r in summary if r["status"] == "OK")
    print(f"\n{ok_count}/{len(summary)} files extracted successfully.")


# ──────────────────────────────────────────────────────────────────────────────
# Compare mode
# ──────────────────────────────────────────────────────────────────────────────

_COMPARE_FIELDS: list[tuple[str, str, str]] = [
    # (display_label, section, field)
    ("Revenue (M)",         "income_statement", "revenue"),
    ("Gross Profit (M)",    "income_statement", "gross_profit"),
    ("EBITDA (M)",          "income_statement", "ebitda"),
    ("Net Income (M)",      "income_statement", "net_income"),
    ("EPS (diluted)",       "income_statement", "eps_diluted"),
    ("Gross Margin %",      "income_statement", "gross_margin"),
    ("EBITDA Margin %",     "income_statement", "ebitda_margin"),
    ("Net Margin %",        "income_statement", "net_margin"),
    ("Total Assets (M)",    "balance_sheet",    "total_assets"),
    ("Total Debt (M)",      "balance_sheet",    "total_debt"),
    ("Cash (M)",            "balance_sheet",    "cash_and_equivalents"),
    ("Net Debt (M)",        "balance_sheet",    "net_debt"),
    ("Total Equity (M)",    "balance_sheet",    "total_equity"),
    ("Operating CF (M)",    "cash_flow",        "operating_cash_flow"),
    ("CapEx (M)",           "cash_flow",        "capex"),
    ("Free CF (M)",         "cash_flow",        "free_cash_flow"),
]


def _compare(path_a: Path, path_b: Path) -> None:
    """Load two extracted JSON files and print a side-by-side YoY delta table.

    Args:
        path_a: Path to the earlier-period JSON (e.g. FY2023).
        path_b: Path to the later-period JSON (e.g. FY2024).
    """
    try:
        data_a: dict = json.loads(path_a.read_text(encoding="utf-8"))
        data_b: dict = json.loads(path_b.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Support both raw financials and the _data.json artifact format
    if "financials" in data_a:
        data_a = data_a["financials"]
    if "financials" in data_b:
        data_b = data_b["financials"]

    co_a: dict = data_a.get("company") or {}
    co_b: dict = data_b.get("company") or {}

    label_a = f"{co_a.get('ticker') or co_a.get('name', path_a.stem)} {co_a.get('period') or co_a.get('fiscal_year', '')}"
    label_b = f"{co_b.get('ticker') or co_b.get('name', path_b.stem)} {co_b.get('period') or co_b.get('fiscal_year', '')}"

    col_label = 22
    col_val = 16
    col_delta = 14

    def _fv(v: object) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:,.2f}"
        return str(v)

    def _delta(a: object, b: object) -> str:
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return "—"
        diff = b - a
        if a != 0:
            pct = (diff / abs(a)) * 100
            sign = "+" if pct >= 0 else ""
            return f"{sign}{pct:.1f}%"
        return "n/a"

    header = (
        "Metric".ljust(col_label) +
        label_a.ljust(col_val) +
        label_b.ljust(col_val) +
        "Change".ljust(col_delta)
    )
    sep = "-" * len(header)

    print(f"\nYoY Comparison: {label_a.strip()}  →  {label_b.strip()}")
    print(sep)
    print(header)
    print(sep)

    for display, section, field in _COMPARE_FIELDS:
        val_a = (data_a.get(section) or {}).get(field)
        val_b = (data_b.get(section) or {}).get(field)
        delta = _delta(val_a, val_b)
        print(
            display.ljust(col_label) +
            _fv(val_a).ljust(col_val) +
            _fv(val_b).ljust(col_val) +
            delta.ljust(col_delta)
        )
    print(sep)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Entry point for the extract CLI."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract financial data from a report and produce structured financial JSON. "
            "Use --batch to process all files in reports/, or --compare to diff two extracted JSONs."
        )
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", metavar="PATH", help="Path to a .txt, .pdf, .png, or .jpg report")
    source.add_argument("--text", metavar="TEXT", help="Report text passed directly as a string")
    source.add_argument("--batch", action="store_true", help="Process all files in reports/ and print a summary table")
    source.add_argument(
        "--compare",
        nargs=2,
        metavar=("BEFORE.json", "AFTER.json"),
        help="Load two extracted JSONs and print a YoY delta table (no API call needed)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save output JSON (and optionally CSV) to the output directory",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=None,
        help="Directory for output files (default: data/ next to extract.py)",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        dest="export_csv",
        help="Also write a flattened CSV alongside the JSON output",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        default="claude-haiku-4-5-20251001",
        help="Claude model to use (default: claude-haiku-4-5-20251001). Use claude-sonnet-4-6 for higher accuracy.",
    )

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging to stderr",
    )
    verbosity.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all stderr output except errors",
    )

    args = parser.parse_args()

    _configure_logging(verbose=args.verbose, quiet=args.quiet)

    # Resolve output directory
    default_out = Path(__file__).parent / "data"
    out_dir = Path(args.output_dir) if args.output_dir else default_out

    # --compare: no API call needed
    if args.compare:
        _compare(Path(args.compare[0]), Path(args.compare[1]))
        return

    # --batch
    if args.batch:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
            sys.exit(1)
        reports_dir = Path(__file__).parent / "reports"
        _batch(reports_dir, out_dir, model=args.model, export_csv=args.export_csv)
        return

    # Single-file / inline-text mode — require source
    if not args.file and not args.text:
        parser.error("one of --file, --text, --batch, or --compare is required")

    # Check API key early
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Read input and extract
    is_image = False
    path: Path | None = None
    text: str | None = None
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        suffix = path.suffix.lower()
        if suffix == _PDF_SUFFIX:
            logger.info("Detected PDF — extracting text: %s", path.name)
            text = _pdf_to_text(path)
        elif suffix in _IMAGE_SUFFIXES:
            is_image = True
        else:
            text = path.read_text(encoding="utf-8")
    else:
        text = args.text

    try:
        if is_image:
            assert path is not None
            logger.info("Detected image — sending to Claude vision: %s", path.name)
            result = extract_from_image(str(path), model=args.model)
        else:
            assert text is not None
            result = extract(text, model=args.model)
    except ValueError as e:
        print(f"Extraction failed:\n{e}", file=sys.stderr)
        sys.exit(1)
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    data = result.financials

    # Surface extraction warnings
    for w in result.extraction_warnings:
        print(f"[EXTRACT] {w}", file=sys.stderr)

    # Validate metadata structure
    for key in EXPECTED_METADATA_KEYS:
        if key not in result.metadata:
            logger.warning("Metadata missing key: %s", key)
        else:
            status = result.metadata[key].get("status")
            if status not in VALID_STATUSES:
                logger.warning("Metadata invalid status for %s: %r", key, status)

    # Coverage summary
    counts: dict[str, int] = {"extracted": 0, "derived": 0, "missing": 0}
    for key in EXPECTED_METADATA_KEYS:
        status = (result.metadata.get(key) or {}).get("status")
        if status in counts:
            counts[status] += 1
    print(
        f"Extraction complete: {counts['extracted']} extracted, "
        f"{counts['derived']} derived, {counts['missing']} missing",
        file=sys.stderr,
    )

    # Validate extracted data
    val_warnings, val_errors = validate_financial_data(data)
    for w in val_warnings:
        print(f"[WARN] {w}", file=sys.stderr)
    for e in val_errors:
        print(f"[ERROR] {e}", file=sys.stderr)
    if val_errors:
        print("Extraction failed validation. Re-run with a more complete input or a more capable model.", file=sys.stderr)
        sys.exit(1)

    output_json = json.dumps(data, indent=2)
    print(output_json)

    # Save if requested
    if args.save:
        json_path, artifact_path = _save_outputs(
            data, result.extraction_warnings, val_warnings, val_errors, out_dir, args.export_csv
        )
        print(f"\nSaved: {json_path}", file=sys.stderr)
        print(f"Data artifact: {artifact_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
