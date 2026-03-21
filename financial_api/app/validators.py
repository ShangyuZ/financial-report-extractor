"""
validators.py — Financial data logical sanity checks.

Works on a plain dict (the JSON payload) so it can be reused
independently of any specific model class.
"""


def validate_financial_data(payload: dict) -> tuple[list[str], list[str]]:
    """Returns (warnings, errors). Errors are blocking; warnings are advisory."""
    warnings: list[str] = []
    errors: list[str] = []

    income = payload.get("income_statement") or {}
    guidance = payload.get("guidance") or {}

    revenue = income.get("revenue")
    gross_profit = income.get("gross_profit")
    ebitda = income.get("ebitda")
    net_income = income.get("net_income")
    gross_margin = income.get("gross_margin")
    ebitda_margin = income.get("ebitda_margin")
    net_margin = income.get("net_margin")

    balance = payload.get("balance_sheet") or {}
    total_debt = balance.get("total_debt")
    cash = balance.get("cash_and_equivalents")
    net_debt = balance.get("net_debt")

    cash_flow = payload.get("cash_flow") or {}
    ocf = cash_flow.get("operating_cash_flow")
    capex = cash_flow.get("capex")
    fcf = cash_flow.get("free_cash_flow")

    # ------------------------------------------------------------------
    # Check: all top-level sections are empty / all fields null
    # ------------------------------------------------------------------
    all_values = [revenue, gross_profit, ebitda, net_income,
                  total_debt, cash, net_debt, ocf, capex, fcf]
    if all(v is None for v in all_values):
        errors.append("All financial fields are null — extraction appears to have completely failed")
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
            errors.append(
                f"Gross profit ({gross_profit:,.2f}) exceeds revenue ({revenue:,.2f}) — logically impossible"
            )

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
    margin_fields = [
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
            implied = (gross_profit / revenue) * 100
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
    pairs = [
        ("revenue", guidance.get("revenue_low"), guidance.get("revenue_high")),
        ("ebitda",  guidance.get("ebitda_low"),  guidance.get("ebitda_high")),
        ("eps",     guidance.get("eps_low"),     guidance.get("eps_high")),
    ]
    for metric, low, high in pairs:
        if low is not None and high is not None and low > high:
            errors.append(
                f"Guidance {metric} low ({low}) > high ({high}) — range is inverted"
            )

    return warnings, errors
