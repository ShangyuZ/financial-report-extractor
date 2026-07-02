"""api.py — FastAPI REST wrapper around the extraction pipeline.

Exposes the extractor as an HTTP service so it can be called from other
applications (dashboards, pipelines, front-ends) rather than only the CLI.

Run:
    uvicorn app.api:app --reload --port 8000

Endpoints:
    GET  /health          Liveness probe.
    POST /extract         Extract financials from a raw text report.
    POST /extract/compare Compare two already-extracted financial payloads.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.extractor import extract
from app.validators import validate_financial_data

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Financial Report Extractor API",
    description="Extract structured, validated financial data from raw report text using Claude.",
    version="0.3.0",
)


class ExtractRequest(BaseModel):
    """Request body for the /extract endpoint."""

    text: str = Field(..., min_length=1, description="Raw financial report text to extract from.")
    model: str = Field(
        "claude-haiku-4-5-20251001",
        description="Claude model identifier. Use claude-sonnet-4-6 for higher accuracy.",
    )


class ExtractResponse(BaseModel):
    """Response body returned by the /extract endpoint."""

    financials: dict
    metadata: dict
    extraction_warnings: list[str]
    validation_warnings: list[str]
    validation_errors: list[str]


class CompareRequest(BaseModel):
    """Request body for the /extract/compare endpoint."""

    before: dict = Field(..., description="Earlier-period financials dict.")
    after: dict = Field(..., description="Later-period financials dict.")


_COMPARE_FIELDS: list[tuple[str, str, str]] = [
    ("revenue", "income_statement", "revenue"),
    ("ebitda", "income_statement", "ebitda"),
    ("net_income", "income_statement", "net_income"),
    ("eps_diluted", "income_statement", "eps_diluted"),
    ("total_debt", "balance_sheet", "total_debt"),
    ("net_debt", "balance_sheet", "net_debt"),
    ("free_cash_flow", "cash_flow", "free_cash_flow"),
]


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness probe. Reports whether the API key is configured."""
    return {"status": "ok", "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(req: ExtractRequest) -> ExtractResponse:
    """Extract structured financials from raw report text.

    Args:
        req: The extraction request containing report text and model choice.

    Returns:
        An :class:`ExtractResponse` with financials, provenance metadata, and
        both extraction and validation warnings/errors.

    Raises:
        HTTPException: 503 if the API key is missing; 422 on extraction failure.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY is not configured on the server.")

    try:
        result = extract(req.text, model=req.model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Extraction failed: {e}") from e

    val_warnings, val_errors = validate_financial_data(result.financials)
    return ExtractResponse(
        financials=result.financials,
        metadata=result.metadata,
        extraction_warnings=result.extraction_warnings,
        validation_warnings=val_warnings,
        validation_errors=val_errors,
    )


@app.post("/extract/compare")
def compare_endpoint(req: CompareRequest) -> dict[str, object]:
    """Compute YoY deltas between two extracted financial payloads.

    Args:
        req: The comparison request holding ``before`` and ``after`` dicts.

    Returns:
        A dict mapping each tracked field to its before/after values and % change.
    """
    before = req.before.get("financials", req.before)
    after = req.after.get("financials", req.after)

    deltas: dict[str, dict] = {}
    for label, section, field in _COMPARE_FIELDS:
        a = (before.get(section) or {}).get(field)
        b = (after.get(section) or {}).get(field)
        pct: float | None = None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a != 0:
            pct = round((b - a) / abs(a) * 100, 1)
        deltas[label] = {"before": a, "after": b, "change_pct": pct}

    return {"deltas": deltas}
