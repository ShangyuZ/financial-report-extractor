"""models.py — Pydantic schema for all financial data extracted from reports."""
from __future__ import annotations

from pydantic import BaseModel, model_validator
from typing import Optional


class CompanyInfo(BaseModel):
    name: str
    ticker: Optional[str] = None
    sector: Optional[str] = None
    fiscal_year: Optional[str] = None
    currency: Optional[str] = "USD"
    period: Optional[str] = None


class IncomeStatement(BaseModel):
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    ebitda: Optional[float] = None
    ebit: Optional[float] = None
    net_income: Optional[float] = None
    eps_diluted: Optional[float] = None
    gross_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    net_margin: Optional[float] = None


class BalanceSheet(BaseModel):
    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    net_debt: Optional[float] = None
    total_equity: Optional[float] = None
    working_capital: Optional[float] = None

    @model_validator(mode="after")
    def derive_net_debt(self) -> BalanceSheet:
        """Derive net_debt = total_debt − cash if both components are present."""
        if self.net_debt is None and self.total_debt is not None and self.cash_and_equivalents is not None:
            self.net_debt = self.total_debt - self.cash_and_equivalents
        return self


class CashFlow(BaseModel):
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = None
    dividends_paid: Optional[float] = None

    @model_validator(mode="after")
    def derive_fcf(self) -> CashFlow:
        """Derive free_cash_flow = operating_cash_flow − capex if both components are present."""
        if self.free_cash_flow is None and self.operating_cash_flow is not None and self.capex is not None:
            self.free_cash_flow = self.operating_cash_flow - self.capex
        return self


class YoYChanges(BaseModel):
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    eps_diluted: Optional[float] = None


class Segment(BaseModel):
    name: str
    revenue: Optional[float] = None
    operating_income: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None


class Guidance(BaseModel):
    revenue_low: Optional[float] = None
    revenue_high: Optional[float] = None
    ebitda_low: Optional[float] = None
    ebitda_high: Optional[float] = None
    eps_low: Optional[float] = None
    eps_high: Optional[float] = None
    commentary: Optional[str] = None


class FinancialData(BaseModel):
    company: CompanyInfo
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
    cash_flow: CashFlow
    yoy_changes: Optional[YoYChanges] = None
    segments: Optional[list[Segment]] = None
    guidance: Optional[Guidance] = None


