"""
tests/test_validators.py — Unit tests for validators.validate_financial_data.

Run with:  python -m pytest financial_api/tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow import without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.validators import validate_financial_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(
    revenue: float | None = 1000.0,
    gross_profit: float | None = 600.0,
    ebitda: float | None = 250.0,
    net_income: float | None = 150.0,
    gross_margin: float | None = 60.0,
    ebitda_margin: float | None = 25.0,
    net_margin: float | None = 15.0,
    total_debt: float | None = 400.0,
    cash: float | None = 200.0,
    net_debt: float | None = 200.0,
    ocf: float | None = 180.0,
    capex: float | None = 50.0,
    fcf: float | None = 130.0,
    guidance: dict | None = None,
) -> dict:
    """Return a minimal but valid-looking financials payload."""
    return {
        "income_statement": {
            "revenue": revenue,
            "gross_profit": gross_profit,
            "ebitda": ebitda,
            "net_income": net_income,
            "gross_margin": gross_margin,
            "ebitda_margin": ebitda_margin,
            "net_margin": net_margin,
        },
        "balance_sheet": {
            "total_debt": total_debt,
            "cash_and_equivalents": cash,
            "net_debt": net_debt,
        },
        "cash_flow": {
            "operating_cash_flow": ocf,
            "capex": capex,
            "free_cash_flow": fcf,
        },
        "guidance": guidance or {},
    }


# ---------------------------------------------------------------------------
# Happy-path: clean payload produces no warnings and no errors
# ---------------------------------------------------------------------------

class TestCleanPayload:
    def test_no_warnings_no_errors_on_valid_data(self):
        payload = _make_payload()
        warnings, errors = validate_financial_data(payload)
        assert warnings == []
        assert errors == []


# ---------------------------------------------------------------------------
# All-null detection
# ---------------------------------------------------------------------------

class TestAllNull:
    def test_all_null_returns_blocking_error(self):
        payload = _make_payload(
            revenue=None, gross_profit=None, ebitda=None, net_income=None,
            total_debt=None, cash=None, net_debt=None, ocf=None, capex=None, fcf=None,
        )
        warnings, errors = validate_financial_data(payload)
        assert len(errors) == 1
        assert "null" in errors[0]

    def test_all_null_returns_early(self):
        """With all null there should be no warnings (early return)."""
        payload = _make_payload(
            revenue=None, gross_profit=None, ebitda=None, net_income=None,
            total_debt=None, cash=None, net_debt=None, ocf=None, capex=None, fcf=None,
        )
        warnings, _ = validate_financial_data(payload)
        assert warnings == []


# ---------------------------------------------------------------------------
# Presence warnings
# ---------------------------------------------------------------------------

class TestPresenceWarnings:
    def test_missing_revenue_warns(self):
        payload = _make_payload(revenue=None, gross_profit=None, gross_margin=None, ebitda_margin=None, net_margin=None)
        warnings, errors = validate_financial_data(payload)
        assert any("Revenue" in w for w in warnings)
        assert errors == []

    def test_missing_net_income_warns(self):
        payload = _make_payload(net_income=None, net_margin=None)
        warnings, _ = validate_financial_data(payload)
        assert any("Net income" in w for w in warnings)

    def test_missing_debt_or_cash_warns(self):
        payload = _make_payload(total_debt=None, net_debt=None)
        warnings, _ = validate_financial_data(payload)
        assert any("debt" in w.lower() or "cash" in w.lower() for w in warnings)

    def test_missing_ocf_or_capex_warns(self):
        payload = _make_payload(ocf=None, fcf=None)
        warnings, _ = validate_financial_data(payload)
        assert any("cash flow" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Revenue ≥ Gross Profit (blocking error)
# ---------------------------------------------------------------------------

class TestRevenueGrossProfitCheck:
    def test_gross_profit_exceeds_revenue_is_error(self):
        payload = _make_payload(revenue=500.0, gross_profit=600.0)
        _, errors = validate_financial_data(payload)
        assert len(errors) == 1
        assert "Gross profit" in errors[0]

    def test_gross_profit_equals_revenue_is_ok(self):
        payload = _make_payload(revenue=600.0, gross_profit=600.0)
        _, errors = validate_financial_data(payload)
        assert errors == []

    def test_gross_profit_below_revenue_is_ok(self):
        payload = _make_payload(revenue=1000.0, gross_profit=400.0)
        _, errors = validate_financial_data(payload)
        assert errors == []


# ---------------------------------------------------------------------------
# EBITDA > Gross Profit (advisory warning)
# ---------------------------------------------------------------------------

class TestEbitdaGrossProfitCheck:
    def test_ebitda_exceeds_gross_profit_warns(self):
        payload = _make_payload(ebitda=700.0, gross_profit=600.0)
        warnings, _ = validate_financial_data(payload)
        assert any("EBITDA" in w and "gross profit" in w for w in warnings)

    def test_ebitda_below_gross_profit_is_ok(self):
        payload = _make_payload(ebitda=200.0, gross_profit=600.0)
        warnings, _ = validate_financial_data(payload)
        assert not any("EBITDA" in w and "gross profit" in w for w in warnings)


# ---------------------------------------------------------------------------
# Net Income > EBITDA (advisory warning)
# ---------------------------------------------------------------------------

class TestNetIncomeEbitdaCheck:
    def test_net_income_exceeds_ebitda_warns(self):
        payload = _make_payload(net_income=300.0, ebitda=250.0)
        warnings, _ = validate_financial_data(payload)
        assert any("Net income" in w and "EBITDA" in w for w in warnings)


# ---------------------------------------------------------------------------
# Margin range checks (0–100%)
# ---------------------------------------------------------------------------

class TestMarginRangeChecks:
    @pytest.mark.parametrize("field,value", [
        ("gross_margin", -5.0),
        ("ebitda_margin", 150.0),
        ("net_margin", -0.1),
    ])
    def test_out_of_range_margin_warns(self, field, value):
        payload = _make_payload(**{field: value})
        warnings, _ = validate_financial_data(payload)
        assert any("outside expected range" in w for w in warnings)

    def test_zero_margin_is_ok(self):
        payload = _make_payload(gross_margin=0.0)
        warnings, _ = validate_financial_data(payload)
        assert not any("outside expected range" in w for w in warnings)

    def test_hundred_percent_margin_is_ok(self):
        payload = _make_payload(gross_margin=100.0)
        warnings, _ = validate_financial_data(payload)
        assert not any("outside expected range" in w for w in warnings)


# ---------------------------------------------------------------------------
# Margin consistency checks
# ---------------------------------------------------------------------------

class TestMarginConsistencyChecks:
    def test_gross_margin_inconsistency_warns(self):
        # gross_profit / revenue = 400/1000 = 40%, stated as 60%
        payload = _make_payload(revenue=1000.0, gross_profit=400.0, gross_margin=60.0)
        warnings, _ = validate_financial_data(payload)
        assert any("Gross margin" in w and "verify" in w for w in warnings)

    def test_gross_margin_within_tolerance_is_ok(self):
        # 600/1000 = 60%, stated as 60.5% → within 1pp
        payload = _make_payload(revenue=1000.0, gross_profit=600.0, gross_margin=60.5)
        warnings, _ = validate_financial_data(payload)
        assert not any("Gross margin" in w and "verify" in w for w in warnings)

    def test_net_margin_inconsistency_warns(self):
        # net_income / revenue = 150/1000 = 15%, stated as 5%
        payload = _make_payload(revenue=1000.0, net_income=150.0, net_margin=5.0)
        warnings, _ = validate_financial_data(payload)
        assert any("Net margin" in w and "verify" in w for w in warnings)


# ---------------------------------------------------------------------------
# Guidance range checks
# ---------------------------------------------------------------------------

class TestGuidanceRangeChecks:
    def test_inverted_revenue_guidance_is_error(self):
        payload = _make_payload(guidance={"revenue_low": 1200.0, "revenue_high": 1000.0})
        _, errors = validate_financial_data(payload)
        assert any("revenue" in e and "inverted" in e for e in errors)

    def test_inverted_eps_guidance_is_error(self):
        payload = _make_payload(guidance={"eps_low": 5.0, "eps_high": 3.0})
        _, errors = validate_financial_data(payload)
        assert any("eps" in e and "inverted" in e for e in errors)

    def test_valid_guidance_range_is_ok(self):
        payload = _make_payload(guidance={"revenue_low": 900.0, "revenue_high": 1100.0})
        _, errors = validate_financial_data(payload)
        assert not any("revenue" in e for e in errors)

    def test_equal_guidance_bounds_is_ok(self):
        # low == high is technically valid (point guidance)
        payload = _make_payload(guidance={"eps_low": 2.5, "eps_high": 2.5})
        _, errors = validate_financial_data(payload)
        assert not any("eps" in e for e in errors)

    def test_partial_guidance_does_not_error(self):
        # Only one bound present — check should be skipped
        payload = _make_payload(guidance={"eps_low": 2.0})
        _, errors = validate_financial_data(payload)
        assert errors == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_payload_raises_no_exception(self):
        warnings, errors = validate_financial_data({})
        # All null path → single error, no exception
        assert len(errors) == 1

    def test_partial_payload_with_only_revenue_no_blocking_error(self):
        payload = {"income_statement": {"revenue": 500.0}}
        warnings, errors = validate_financial_data(payload)
        assert errors == []

    def test_zero_revenue_skips_margin_consistency(self):
        # Revenue = 0 should not trigger division-by-zero
        payload = _make_payload(revenue=0.0, gross_profit=0.0)
        warnings, errors = validate_financial_data(payload)
        # Gross profit (0) does not exceed revenue (0) → no error
        assert not any("Gross profit" in e for e in errors)

    def test_negative_net_income_no_crash(self):
        payload = _make_payload(net_income=-50.0, net_margin=-5.0)
        warnings, errors = validate_financial_data(payload)
        # Negative net income is valid; should not produce a blocking error
        assert errors == []
