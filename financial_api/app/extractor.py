import os
import json
import re
import base64
from pathlib import Path
from dataclasses import dataclass, field

from app.models import FinancialData

SCHEMA_HINT = """
{
  "company": {
    "name": "string",
    "ticker": "string or null",
    "sector": "string or null",
    "fiscal_year": "string (e.g. '2024') or null",
    "currency": "string or null (default 'USD')",
    "period": "string or null (e.g. 'FY2024')"
  },
  "income_statement": {
    "revenue": "float (millions USD) or null",
    "gross_profit": "float or null",
    "ebitda": "float or null",
    "ebit": "float or null",
    "net_income": "float or null",
    "eps_diluted": "float or null",
    "gross_margin": "float (%) or null",
    "ebitda_margin": "float (%) or null",
    "net_margin": "float (%) or null"
  },
  "balance_sheet": {
    "total_assets": "float or null",
    "total_debt": "float or null",
    "cash_and_equivalents": "float or null",
    "net_debt": "float or null",
    "total_equity": "float or null",
    "working_capital": "float or null"
  },
  "cash_flow": {
    "operating_cash_flow": "float or null",
    "capex": "float or null",
    "free_cash_flow": "float or null",
    "dividends_paid": "float or null"
  },
  "yoy_changes": {
    "revenue": "float (%) or null",
    "ebitda": "float (%) or null",
    "net_income": "float (%) or null",
    "eps_diluted": "float (%) or null"
  },
  "segments": [
    {
      "name": "string",
      "revenue": "float or null",
      "operating_income": "float or null",
      "revenue_growth_yoy": "float (%) or null"
    }
  ],
  "guidance": {
    "revenue_low": "float or null",
    "revenue_high": "float or null",
    "ebitda_low": "float or null",
    "ebitda_high": "float or null",
    "eps_low": "float or null",
    "eps_high": "float or null",
    "commentary": "string or null"
  }
}
"""

_PROMPT_TEMPLATE = """\
Extract financial data from the financial report below and return a single JSON object with this exact structure:

{{
  "financials": <object matching the schema below>,
  "metadata": {{
    "company.name":                       {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "company.ticker":                     {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "company.fiscal_year":                {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.revenue":           {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.gross_profit":      {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.ebitda":            {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.ebit":              {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.net_income":        {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.eps_diluted":       {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.gross_margin":      {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.ebitda_margin":     {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "income_statement.net_margin":        {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "balance_sheet.total_assets":         {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "balance_sheet.total_debt":           {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "balance_sheet.cash_and_equivalents": {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "balance_sheet.net_debt":             {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "balance_sheet.total_equity":         {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "cash_flow.operating_cash_flow":      {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "cash_flow.capex":                    {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "cash_flow.free_cash_flow":           {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "cash_flow.dividends_paid":           {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "guidance.revenue_low":               {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "guidance.revenue_high":              {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "guidance.eps_low":                   {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}},
    "guidance.eps_high":                  {{"source": <exact quoted phrase|null>, "status": <"extracted"|"derived"|"missing">, "reason": <"not found in document"|null>}}
  }},
  "extraction_warnings": [<string>]
}}

FINANCIALS SCHEMA:
{schema}

RULES:
- Return ONLY valid JSON. No markdown fences, no commentary.
- NEVER invent or estimate numbers. If a field is not clearly stated, set it to null.
- All monetary values must be in millions USD (convert: $4.85bn → 4850.0, $250M → 250.0).
- Percentages are plain numbers (8.2% → 8.2, not 0.082).
- For "source": quote the shortest phrase from the report that directly supports the value (max 120 chars). Use null if status is "missing".
- For "status":
    "extracted" = value is directly stated in the report
    "derived"   = value was computed from other extracted fields (e.g. net_debt = total_debt - cash)
    "missing"   = not found in the report
- For "reason": use "not found in document" when status is "missing". Use null for "extracted" or "derived".
- Use extraction_warnings for: a figure appears multiple times with different values, currency is ambiguous, period is unclear.
- If no segments are mentioned, return "segments": [].
- If no guidance is mentioned, return all guidance fields as null.
"""


@dataclass
class ExtractionResult:
    financials: dict
    metadata: dict
    extraction_warnings: list[str] = field(default_factory=list)


def _build_prompt(text: str) -> str:
    return _PROMPT_TEMPLATE.format(schema=SCHEMA_HINT) + f"\nReport text:\n{text}"


def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```[a-z]*\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    return json.loads(raw)


def _finalise(parsed: dict) -> ExtractionResult:
    if "financials" not in parsed:
        raise ValueError("Extraction response is missing the 'financials' key.")
    validated = FinancialData.model_validate(parsed["financials"])
    return ExtractionResult(
        financials=validated.model_dump(),
        metadata=parsed.get("metadata", {}),
        extraction_warnings=parsed.get("extraction_warnings", []),
    )


def _call_api(client, model: str, messages: list) -> str:
    message = client.messages.create(
        model=model,
        max_tokens=2500,
        temperature=0,
        messages=messages,
    )
    if message.stop_reason == "max_tokens":
        raise ValueError(
            "Extraction truncated due to token limit. "
            "Try shorter input or split the document."
        )
    return message.content[0].text


def _with_retry(client, model: str, messages: list) -> dict:
    raw = _call_api(client, model, messages)
    try:
        return _parse_response(raw)
    except json.JSONDecodeError:
        # Single retry — occasional structured output failures recover on a second attempt
        raw = _call_api(client, model, messages)
        try:
            return _parse_response(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Claude returned invalid JSON after retry: {e}\n\nRaw response:\n{raw}")


EXPECTED_METADATA_KEYS = {
    "company.name",
    "company.ticker",
    "company.fiscal_year",
    "income_statement.revenue",
    "income_statement.gross_profit",
    "income_statement.ebitda",
    "income_statement.ebit",
    "income_statement.net_income",
    "income_statement.eps_diluted",
    "income_statement.gross_margin",
    "income_statement.ebitda_margin",
    "income_statement.net_margin",
    "balance_sheet.total_assets",
    "balance_sheet.total_debt",
    "balance_sheet.cash_and_equivalents",
    "balance_sheet.net_debt",
    "balance_sheet.total_equity",
    "cash_flow.operating_cash_flow",
    "cash_flow.capex",
    "cash_flow.free_cash_flow",
    "cash_flow.dividends_paid",
    "guidance.revenue_low",
    "guidance.revenue_high",
    "guidance.eps_low",
    "guidance.eps_high",
}

VALID_STATUSES = {"extracted", "derived", "missing"}


def extract(text: str, model: str = "claude-haiku-4-5-20251001") -> ExtractionResult:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(text)
    messages = [{"role": "user", "content": prompt}]
    parsed = _with_retry(client, model, messages)
    return _finalise(parsed)


def extract_from_image(image_path: str, model: str = "claude-haiku-4-5-20251001") -> ExtractionResult:
    """Extract financial data from an image file (PNG, JPG, JPEG)."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    path = Path(image_path)
    suffix = path.suffix.lower()
    media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    media_type = media_type_map.get(suffix)
    if not media_type:
        raise ValueError(f"Unsupported image format: {suffix}. Supported: .png, .jpg, .jpeg")

    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)
    prompt_text = _PROMPT_TEMPLATE.format(schema=SCHEMA_HINT)

    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
            {"type": "text", "text": prompt_text},
        ],
    }]
    parsed = _with_retry(client, model, messages)
    return _finalise(parsed)
