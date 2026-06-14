"""
validators.py — Financial data logical sanity checks.

Works on a plain dict (the JSON payload) so it can be reused
independently of any specific model class.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def validate_financial_data(payload: dict) -> tuple[list[str], list[str]]:
    """Run logical sanity checks on an extracted financials dict.

    Args:
        payload: The ``financials`` dict produced by the extractor (not the full
                 artifact — just the financials block).

    Returns:
        A ``(warnings, errors)`` tuple.  Errors are blocking issues that indicate
        a fundamentally invalid extraction; warnings are advisory and do not block
        downstream use of the data.
    """
    warnings: list[str] = []
    errors: list[str] = []

    income: dict = payload.get("income_statement") or {}
    guidance: dict = payload.get("guidance") or {}

    revenue: float | None = income.get("revenue")
    gross_profit: float | None = income.get("gross_profit")
    ebitda: float | None = income.get("ebitda")
    net_income: float | None = income.get("net_income")
    gross_margin: float | None = income.get("gross_margin")
    ebitda_margin: float | None = income.get("ebitda_margin")
    net_margin: float | None = income.get("net_margin")

    balance: dict = payload.get("balance_sheet") or {}
    total_debt: float | None = balance.get("total_debt")
    cash: float | None = balance.get("cash_and_equivalents")
    net_debt: float | None = balance.get("net_debt")

    cash_flow: dict = payload.get("cash_flow") or {}
    ocf: float | None = cash_flow.get("operating_cash_flow")
    capex: float | None = cash_flow.get("capex")
    fcf: float | None = cash_flow.get("free_cash_flow")

    # ------------------------------------------------------------------
    # Check: all top-level sections are empty / all fields null
    # ------------------------------------------------------------------
    all_values: list[float | None] = [revenue, gross_profit, ebitda, net_income,
                                       total_debt, cash, net_debt, ocf, capex, fcf]
    if all(v is None for v in all_values):
        errors.append("All financial fields are null — extraction appears to have completely failed")
        logger.error("Validation: all financial fields are null")
        # Return early; remaining checks are meaningless
        return warnings, errors

    # ------------------------------------------------------------------
    # Presence checks (warnings)
    # ------------------------------------------------------------------
    if revenue is None:
        warnings.append("Revenue is missing — core profitability metrics will be incomplete")
    if net_income is None:
        warnings.append("Net income is missing — FCF quality cannot be assessed")
    if net_debt is None and (total_debt is None or cash is None):
        warnings.append("Total debt or cash is missing — net debt cannot be derived")
    if fcf is None and (ocf is None or capex is None):
        warnings.append("Operating cash flow or capex is missing — free cash flow cannot be derived")

    # ------------------------------------------------------------------
    # Revenue ≥ Gross Profit (ERROR)
    # ------------------------------------------------------------------
    if revenue is not None and gross_profit is not None:
        if gross_profit > revenue:
            msg = (
                f"Gross profit ({gross_profit:,.2f}) exceeds revenue ({revenue:,.2f}) — logically impossible"
            )
            errors.append(msg)
            logger.error("Validation error: %s", msg)

    # ------------------------------------------------------------------
    # Gross Profit ≥ EBITDA (WARNING — unusual but possible)
    # ------------------------------------------------------------------
    if gross_profit is not None and ebitda is not None:
        if ebitda > gross_profit:
            warnings.append(
                f"EBITDA ({ebitda:,.2f}) exceeds gross profit ({gross_profit:,.2f}) — unusual, verify D&A treatment"
            )

    # ------------------------------------------------------------------
    # EBITDA ≥ Net Income (WARNING — unusual but possible)
    # ------------------------------------------------------------------
    if ebitda is not None and net_income is not None:
        if net_income > ebitda:
            warnings.append(
                f"Net income ({net_income:,.2f}) exceeds EBITDA ({ebitda:,.2f}) — unusual, verify tax/interest items"
            )

    # ------------------------------------------------------------------
    # Margin range 0–100% (WARNING)
    # ------------------------------------------------------------------
    margin_fields: list[tuple[str, float | None]] = [
        ("Gross margin", gross_margin),
        ("EBITDA margin", ebitda_margin),
        ("Net margin", net_margin),
    ]
    for label, value in margin_fields:
        if value is not None and not (0.0 <= value <= 100.0):
            warnings.append(
                f"{label} of {value:.1f}% is outside expected range (0–100%) — likely extraction error"
            )

    # ------------------------------------------------------------------
    # Margin consistency: stated vs. computable (WARNING)
    # Tolerance of 1.0pp to absorb rounding differences.
    # ------------------------------------------------------------------
    if revenue is not None and revenue > 0:
        if gross_profit is not None and gross_margin is not None:
            implied: float = (gross_profit / revenue) * 100
            if abs(implied - gross_margin) > 1.0:
                warnings.append(
                    f"Gross margin stated as {gross_margin:.1f}% but gross_profit / revenue implies "
                    f"{implied:.1f}% — verify source"
                )
        if net_income is not None and net_margin is not None:
            implied = (net_income / revenue) * 100
            if abs(implied - net_margin) > 1.0:
                warnings.append(
                    f"Net margin stated as {net_margin:.1f}% but net_income / revenue implies "
                    f"{implied:.1f}% — verify source"
                )

    # ------------------------------------------------------------------
    # Guidance low ≤ high (ERROR)
    # ------------------------------------------------------------------
    pairs: list[tuple[str, float | None, float | None]] = [
        ("revenue", guidance.get("revenue_low"), guidance.get("revenue_high")),
        ("ebitda",  guidance.get("ebitda_low"),  guidance.get("ebitda_high")),
        ("eps",     guidance.get("eps_low"),     guidance.get("eps_high")),
    ]
    for metric, low, high in pairs:
        if low is not None and high is not None and low > high:
            msg = f"Guidance {metric} low ({low}) > high ({high}) — range is inverted"
            errors.append(msg)
            logger.error("Validation error: %s", msg)

    logger.debug(
        "Validation complete: %d warning(s), %d error(s)",
        len(warnings),
        len(errors),
    )
    return warnings, errors
