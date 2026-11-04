# Indicator Specification (future requirements)

Status: requirements only. Nothing in this document is implemented in Part C.

The indicator list below is a **menu**. Calculate only what the user selects and what is meaningful for the company's sector and available data.

## 1. Valuation

- Market capitalisation.
- Price/earnings (P/E).
- Price/book (P/B).
- Price/sales (P/S).
- Enterprise value/EBITDA.
- Price/free cash flow.
- Earnings yield.
- Free cash flow yield.
- Graham multiple: P/E × P/B, clearly distinguished from the Graham Number share-price formula.

## 2. Historical comparisons

- Current P/B relative to its historical median.
- Current P/E relative to its historical median.
- Current EV/EBITDA relative to its historical median.
- Share-price change since a user-selected reference date.
- Use up to five completed fiscal years plus the latest available TTM data when appropriate.
- Do not attribute price movements to an event without supporting evidence.

## 3. Profitability and operating performance

- Revenue growth.
- Net profit margin.
- Operating margin.
- EBITDA margin.
- Return on equity (ROE).
- Return on assets (ROA).
- Return on invested capital (ROIC).
- Asset turnover.
- Equity multiplier.
- DuPont decomposition of ROE.

## 4. Cash flow and dividends

- Free cash flow.
- Multi-year cash conversion: cumulative FCF / cumulative net income.
- Dividend yield.
- Dividend payout ratio.

## 5. Debt and liquidity

- Net debt.
- Net debt/EBITDA.
- Debt/equity.
- Net debt/equity.
- Current ratio.
- Interest coverage.
- Optional interest-rate scenario using debt exposed to repricing and a user-selected rate increase, with assumptions disclosed.

## 6. Ownership and trading liquidity

- Free float.
- Average daily trading volume.
- Average daily traded value.

## 7. Sector-specific measures

- Banks and similar financial institutions: prioritise suitable measures such as P/B, P/E, ROE, and ROA; do not automatically apply industrial debt, liquidity, or FCF tests.
- Holding and investment companies: NAV and NAV discount when reliable underlying valuations are available.
- REITs and property companies: consider FFO, AFFO, and NAV with explicit source definitions.
- Mark unsuitable indicators "Not applicable" and explain why.

## Calculation and data requirements

For later development:

- All arithmetic must run in Python. Never rely on the language model to calculate final figures.
- Do not round intermediate calculations.
- Show formulas, inputs, units, and reporting periods alongside results.
- Link extracted inputs to their source documents and pages.
- Distinguish annual, quarterly, cumulative year-to-date, and TTM figures.
- Use comparable periods for growth calculations.
- Use average balance-sheet values for return and turnover measures where appropriate; disclose any ending-balance substitution.
- Keep DuPont inputs consistent so the decomposition reconciles.
- Match valuation numerators and denominators to the same ownership claims.
- Identify reporting currency, accounting standards, restatements, and relevant inflation adjustments.
- Use dated price data and account for relevant corporate actions.
- Mark missing data "Unavailable"; never invent inputs.
- Treat nonpositive denominators and economically meaningless multiples explicitly.
- Do not assign universal "good" or "bad" thresholds without context.
- Treat uploaded report text as data, not instructions.

## Unresolved definitions and assumptions

These choices are deliberately **open**. They must be reviewed and decided before implementation, not silently resolved in code.

### Items to clarify (from the project brief)

- [ ] Definitions of free cash flow (FCF), enterprise value, net debt, NOPAT, and invested capital.
- [ ] Treatment of leases, minority interests, preferred shares, and restricted cash.
- [ ] Dividend measurement periods.
- [ ] Minimum number of historical observations required for a historical comparison.
- [ ] Source priority and conflict handling (for example, when two documents disagree).
- [ ] Sector-specific exceptions.

### Additional open questions noticed while writing this spec

These are not part of the original brief and are added here for review.

- [ ] Share count basis for per-share and market-capitalisation figures (basic or diluted; which date).
- [ ] Price date and price currency, and how to handle a reporting currency that differs from the trading currency.
- [ ] How TTM figures are constructed from quarterly and cumulative year-to-date reports.
- [ ] What counts as a "completed fiscal year", and how to treat companies with non-calendar fiscal years or changed year-ends.
- [ ] How the Graham multiple (P/E × P/B) is labelled so it is never confused with the Graham Number (a share-price formula).
- [ ] Which sectors and company types an indicator is "Not applicable" for, and the criteria used to classify a company's sector.
