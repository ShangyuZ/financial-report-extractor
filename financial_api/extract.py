#!/usr/bin/env python3
"""
extract.py — CLI tool: raw report → structured financial JSON

Supported input formats:
  --file report.txt          Plain text
  --file report.pdf          PDF (text extracted automatically via pypdf)
  --file report.png          Image — PNG, JPG, JPEG (sent to Claude vision API)
  --text "Revenue was ..."   Inline text string
"""

import argparse
import json
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

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_PDF_SUFFIX = ".pdf"


def _pdf_to_text(path: Path) -> str:
    try:
        import pypdf
    except ImportError:
        print("Error: pypdf is required for PDF support. Install with: pip install pypdf", file=sys.stderr)
        sys.exit(1)
    reader = pypdf.PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def main():
    parser = argparse.ArgumentParser(
        description="Extract financial data from a report and produce structured financial JSON."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", metavar="PATH", help="Path to a text file containing the report")
    source.add_argument("--text", metavar="TEXT", help="Report text passed directly as a string")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save output to data/{TICKER}_{FY}.json",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        default="claude-haiku-4-5-20251001",
        help="Claude model to use (default: claude-haiku-4-5-20251001). Use claude-sonnet-4-6 for higher accuracy.",
    )
    args = parser.parse_args()

    # Check API key early
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Read input and extract
    is_image = False
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        suffix = path.suffix.lower()
        if suffix == _PDF_SUFFIX:
            print(f"Detected PDF — extracting text...", file=sys.stderr)
            text = _pdf_to_text(path)
        elif suffix in _IMAGE_SUFFIXES:
            is_image = True
            text = None
        else:
            text = path.read_text(encoding="utf-8")
    else:
        text = args.text

    try:
        if is_image:
            print(f"Detected image — sending to Claude vision...", file=sys.stderr)
            result = extract_from_image(str(path), model=args.model)
        else:
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
            print(f"[WARN] Metadata missing key: {key}", file=sys.stderr)
        else:
            status = result.metadata[key].get("status")
            if status not in VALID_STATUSES:
                print(f"[WARN] Metadata invalid status for {key}: {status!r}", file=sys.stderr)

    # Coverage summary
    counts = {"extracted": 0, "derived": 0, "missing": 0}
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
    saved_path = None
    if args.save:
        ticker = (data.get("company") or {}).get("ticker") or "UNKNOWN"
        fy = (data.get("company") or {}).get("fiscal_year") or "UNKNOWN"
        out_dir = Path(__file__).parent / "data"
        out_dir.mkdir(exist_ok=True)

        # financials-only JSON — clean structured output
        saved_path = out_dir / f"{ticker}_{fy}.json"
        saved_path.write_text(output_json, encoding="utf-8")
        print(f"\nSaved: {saved_path}", file=sys.stderr)

        # _data.json artifact — full provenance record
        artifact = {
            "financials": data,
            "metadata": result.metadata,
            "extraction_warnings": result.extraction_warnings,
            "validation_warnings": val_warnings,
            "validation_errors": val_errors,
        }
        artifact_path = out_dir / f"{ticker}_{fy}_data.json"
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(f"Data artifact: {artifact_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
