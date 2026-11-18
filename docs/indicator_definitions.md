# Global Company Analysis: Indicator Definitions and Calculation Rules

Version 1.0 — 18 November 2026. Provided by the project team. This document is the authoritative source for indicator definitions and calculation rules; where `docs/indicator_spec.md` differs, this document wins (see "Changes introduced by Indicator Definitions v1.0" in that file).

## 1. Implementation prompt

Use this document as the indicator catalogue and calculation specification for the existing three-agent company-analysis application. Implement the definitions consistently and retain the source data, assumptions and calculation trail for every result. These are application conventions; where financial practice permits different definitions, do not switch between them silently.

The user enters a company name or ticker. Agent 1 automatically finds the company's financial reports, extracts the figures and calculates the predefined indicators plus any additional indicators requested by the user. Agent 2 reviews earnings calls and relevant news, obtaining transcripts or transcribing recordings and translating material when necessary. Agent 3 combines both analyses into a single sourced report, explaining material relationships, risks, inconsistencies and missing information. Uploading reports must remain optional.

Apply the general indicator set to suitable operating companies. Activate holding-company and banking indicators according to the company's economic business model. Do not force an unsuitable metric onto a company. Keep providers and API credentials configurable. Preserve the existing application architecture unless a change is required to implement this specification.

## 2. Financial-report sourcing

### Primary source: the company's Investor Relations website

1. Resolve the correct legal entity, official website, exchange, security and share class. Ask for clarification if the identity is ambiguous.
2. Start with the company's official Investor Relations section. Relevant pages may be labelled Financial Results, Quarterly Results, Annual Reports, Reports and Presentations, Financial Information or Regulatory Filings.
3. Retrieve the latest available financial statements, annual and interim reports, earnings releases and accompanying notes. Retrieve sufficient historical reports for the requested calculations. Prefer complete statements and notes over presentation slides for accounting inputs.
4. Confirm the reporting period, publication date, consolidation scope, currency, units and accounting framework. Confirm that the document concerns the selected company rather than a similarly named subsidiary.
5. Keep the original document and its exact source URL, document title, publication date and relevant page/table references. Use the latest applicable amended or restated official document and retain the reason for any replacement.

### Official filing fallback and cross-check

If a report is unavailable, incomplete or inaccessible on the Investor Relations website, use the relevant regulator's filing database or the exchange's official disclosure service. An official amended filing takes precedence over an older inconsistent copy on the company website; retrieval preference must not override document authority.

SEC EDGAR is the Securities and Exchange Commission's public corporate-filing database. Use it for companies that file there. Relevant documents include Form 10-K annual reports, Form 10-Q quarterly reports, Form 20-F annual reports, and financial-results releases or attachments submitted through Forms 8-K or 6-K. A 6-K is not automatically a quarterly financial report: inspect its contents and reporting period. Use the entity's CIK to disambiguate issuers when available. EDGAR is an applicable official source, not a requirement for every company.

For automated EDGAR access, declare an identifying User-Agent containing an application or organisation name and a genuine contact address. Do not invent a contact address. Respect the SEC's current fair-access policy; its published maximum is 10 requests per second in aggregate. Use a conservative configurable rate, caching and backoff. If required identification is missing, show a configuration message and continue through other permitted sources where possible.

Configured EDGAR contact email: stored only in the local `.env` file as `SEC_CONTACT_EMAIL` (never in tracked files).
Use the following identification header for automated EDGAR requests, built from configuration:

`User-Agent: <SEC_APP_NAME> <SEC_CONTACT_EMAIL>` (default application name: FinancialAnalysisAgent)

Keep this contact configurable. Use the address only as contact identification; no email password or mailbox access is required. Setting this header does not authorise sending email.

### Secondary sources and uploads

Use reputable financial-data services or document repositories only when necessary, or for cross-checking. Label the source and definition. Do not silently replace report-derived figures with a vendor ratio that uses different periods or accounting conventions. Treat search-result snippets as discovery aids, not sufficient evidence for a calculation. User uploads are an optional fallback and must undergo the same identity, period and scope checks.

### Earnings calls and news

For earnings calls, start with the company's Investor Relations results or events archive, including prepared remarks, presentations, transcripts and recordings. Use reputable transcript providers when an official transcript is unavailable. If permitted recordings are available without transcripts, transcribe them. Preserve the original language, translation, speaker attribution and timestamps where available; flag uncertain transcription. Distinguish management statements, analyst questions and independently verified facts.

Review news relevant to the company, its subsector, operating locations, customer markets, supply chain, commodity exposure, financing and regulatory or sanctions exposure. Listing location alone does not determine relevance. Use credible reporting and relevant primary announcements. News-provider selection will be determined later when the API integrations are configured. State the publication date and the plausible business transmission channel rather than attaching unrelated political news.

## 3. Common calculation and reporting rules

### Data and provenance

Every input must carry its value, unit, currency, period start/end, publication date, source URL, page/table, consolidation scope, accounting framework and restatement status. Every calculated output must carry its indicator identifier, definition version, formula, input references, result, unit, period and status.

Statuses: `calculated`, `reported_only`, `estimated`, `missing`, `not_applicable`, `not_meaningful`, `not_comparable`. Use NM for a mathematically possible but economically meaningless ratio. Missing data is not zero. A negative result is not automatically missing. Explain invalid denominators and sector exclusions.

Extract financial amounts directly from statements and notes. Do not reverse-engineer verified revenue, profit, debt or assets from rounded published multiples. Keep reported and adjusted measures separate, with a reconciliation for adjustments. Consolidated operating measures use consolidated inputs; common-equity measures use the income and equity attributable to the relevant common shareholders. Record non-controlling interests (NCI) and preferred interests separately.

### Periods and averages

- Income-statement and cash-flow measures default to trailing twelve months (TTM). Balance-sheet inputs use the latest published period-end balance; never sum balance sheets into TTM amounts.
- TTM equals the latest four non-overlapping quarters, or latest full fiscal year + current year-to-date period − comparable prior year-to-date period. Apply the same twelve-month principle to half-year reporters. Explain 52/53-week years, year-end changes and incomplete periods.
- Do not blindly add or subtract cumulative per-share figures with different share bases. Use appropriately adjusted published quarterly EPS or a valid numerator/denominator reconstruction.
- Average balance-sheet amount means the average of the opening and closing balances covering the same twelve-month period. A consistent quarterly average may be used when available and seasonality matters; identify the method. If opening data is unavailable, do not invent an average. Label any closing-balance approximation separately.
- Target five completed fiscal years plus current TTM. Three years is a reasonable default for a basic trend; use less history when necessary and disclose the limitation. A five-year measure requires five actual years of aligned data.
- Save the analysis date. A historical as-of analysis must exclude documents not yet published at that date. Distinguish current restated history from information available at the historical date.

### Prices, shares and currencies

- Default price: the latest completed trading session's closing price. Record exchange, timestamp, time zone, currency and delay. Label live prices separately. Judge freshness against the expected latest session, accounting for market holidays, weekends and trading suspensions.
- Price returns use split-adjusted prices without cash-dividend reinvestment. Total shareholder returns require a separate dividend-reinvested series.
- Market capitalisation uses verified shares outstanding near the valuation date, excluding treasury shares and incorporating verified subsequent issuance or repurchases. EPS uses period-specific weighted-average basic or diluted shares. Store both bases.
- For TTM diluted EPS, prefer consistently adjusted published quarterly figures or a standards-consistent calculation. Do not create dilution errors by simply averaging quarterly diluted share counts.
- Sum economically distinct share classes for company market capitalisation. Do not count multiple listings of the same underlying shares twice. Align ADR/depositary-receipt prices, dividends and share counts to the underlying-share conversion ratio. Allocate earnings and equity appropriately where classes have different economic rights.
- Default to the company's reporting currency. If the share price is quoted in another currency, translate market capitalisation into the reporting currency using the valuation-date spot rate. Debt and cash remain the latest reported balances; show their date relative to the valuation date.
- When translating an entire set of statements into a presentation currency, use period-end rates for balances and suitable period-average or transaction rates for flows. This is distinct from aligning currencies for a valuation at one date. Record FX source, date, direction and quotation subunits such as cents or pence.
- Calculate growth using consistent currency and accounting bases. Show constant-currency growth only when disclosed or reproducibly calculable.

### Comparability and presentation

Record material differences involving accounting frameworks, lease accounting, inflation accounting, capitalised development costs and revaluations. Translation alone does not make accounting figures comparable. If reliable normalisation is unavailable, flag the limitation instead of implying equivalence.

Do not round intermediate calculations. Round only display values, normally to two decimal places for multiples and percentages, with suitable scaling for amounts. Distinguish percentage changes from percentage-point changes. A low multiple alone is not a buy signal; interpret it with business quality, growth, capital intensity and risk. Do not hide missing data by assigning a neutral score.

## 4. Fundamental financial definitions

| Identifier | Definition / calculation | Required convention |
|---|---|---|
| `revenue` | Consolidated revenue or sales. | Do not substitute deposits or loan balances for bank revenue. |
| `net_income_group` | Total consolidated net income for the period. | Includes NCI; use with consolidated assets, cash flows and group margins. |
| `net_income_common` | Net income attributable to the parent's common shareholders. | Exclude NCI and account for preferred dividends or other relevant participation rights; use for P/E and common ROE. |
| `equity_common` | Book equity attributable to the parent's common shareholders. | Exclude NCI and preferred equity; denominator for P/B. |
| `equity_total` | Total consolidated equity. | Includes NCI; use for group leverage and group DuPont analysis. |
| `assets_total` | Consolidated total assets. | Obtain directly from the balance sheet, not by dividing profit by ROA. |
| `market_cap` | Sum of price × outstanding shares for each economically distinct common share class. | Distinguish total market capitalisation from free-float capitalisation. |
| `debt_ex_leases` | Interest-bearing short- and long-term borrowings, including current maturities. | Do not automatically include trade payables or provisions. Assess debt-like supplier-finance arrangements separately. |
| `lease_liabilities` | Recognised operating and finance lease liabilities, current and non-current. | Do not add a lease amount twice if already included in borrowings. |
| `debt_inc_leases` | `debt_ex_leases` + `lease_liabilities`. | Main debt view includes leases; retain an additional excluding-leases view. |
| `cash_eligible` | Unrestricted cash and cash equivalents. | Exclude restricted cash. Keep short-term investments separate by default; identify any expanded net-debt definition explicitly. |
| `net_debt` | `debt_inc_leases` − `cash_eligible`. | A negative result is net cash; do not floor it at zero. Also retain an excluding-leases view. |
| `enterprise_value` | `market_cap` + `debt_inc_leases` + preferred capital + NCI value − `cash_eligible`. | Prefer observable debt market values where available; otherwise disclose book-value proxies. Identify valuation bases for preferred capital and NCI. |
| `operating_ev` | `enterprise_value` − separately valued non-operating investments/interests. | Also remove corresponding investment income or earnings from the operating denominator. Keep this adjusted view distinct from the base EV. |
| `ebit` | Operating earnings before interest and tax. | Explain classification of FX items and investment income. Reconcile to reported operating profit if different. |
| `depreciation_amortisation` | Depreciation and amortisation charged in arriving at EBIT. | Avoid double counting. Do not automatically treat impairments as depreciation. |
| `ebitda` | EBIT + relevant depreciation and amortisation. | Company-reported Adjusted EBITDA is separate. Do not automatically add back share-based compensation. |
| `nopat` | EBIT × (1 − suitable operating tax rate). | Use directly attributable operating tax where available; otherwise use a disclosed normalised rate reflecting the operations. Do not apply a universal tax rate or assume tax benefits on losses. |
| `invested_capital` | Consolidated equity + interest-bearing debt including leases − eligible cash − non-operating financial investments. | Include NCI and equity-classified preferred interests; do not duplicate debt-classified preferred instruments. Include goodwill in the main view. Label approximations where investment separation is incomplete. |
| `capex` | Cash expenditure on long-term tangible and intangible operating assets. | Positive spending amount. Include capitalised software/development; exclude business acquisitions and financial investments. Do not net asset-sale proceeds against main Capex. Exclude non-cash lease inception. |
| `cfo_reported` | Reported cash flow from operating activities. | Record classifications of interest, dividends and lease payments. |
| `cfo_standardised` | CFO adjusted to an after-cash-interest and after-lease-principal basis for comparison. | Subtract cash interest and lease principal classified outside CFO; add back shareholder dividends classified inside CFO. Where identifiable, remove interest/dividend receipts from CFO and present them separately. Never deduct an item already included. Retain an adjustment bridge; disclose tax-allocation limitations. |
| `fcf_reported` | `cfo_reported` − `capex`. | Simple statement-based FCF; classification differences may prevent direct comparison. |
| `fcf_standardised` | `cfo_standardised` − `capex`. | Main comparative FCF: after interest and lease cash payments, before debt proceeds/repayments and shareholder distributions. Do not label it strict FCFE. If adjustments are unavailable, show reported FCF with limitations. |
| `operating_nwc` | Non-cash operating current assets − non-interest-bearing operating current liabilities. | Exclude cash, financial investments and financing debt; maintain consistent account mapping across periods. |
| `fcff` | NOPAT + D&A − Capex − increase in operating NWC. | Separate DCF cash-flow measure. Align lease-financing treatment, operating earnings, lease amortisation and capital base. Do not automatically produce FCFF/DCF where reliable lease normalisation is unavailable. Separate acquisition, FX and other non-cash NWC movements where possible. |

Adding NCI to EV aligns consolidated operating earnings with the ownership claims being valued. Including leases in debt does not, by itself, make EBITDA comparable across accounting frameworks. Identify whether operating lease expense remains in EBITDA and how lease amortisation is treated. If an equivalent basis cannot be established, mark the comparison `not_comparable`.

## 5. Core indicators

Unless specified otherwise, flow measures are TTM. In comparative indicators, FCF means `fcf_standardised`; label reported-basis alternatives explicitly. Average follows Section 3.

| Indicator | Formula / definition | Interpretation and limitations |
|---|---|---|
| Price/earnings — P/E | `market_cap` / `net_income_common` | Common-equity valuation relative to earnings. If earnings ≤ 0, NM; negative P/E is not a cheapness signal. |
| Price/sales — P/S | `market_cap` / `revenue` | Equity valuation relative to sales; does not incorporate debt. Revenue must be positive. |
| Price/book — P/B | `market_cap` / `equity_common` | Equity valuation relative to common book equity. If equity ≤ 0, NM. |
| Price/free cash flow — P/FCF | `market_cap` / FCF | Equity valuation relative to cash generation. If FCF ≤ 0, multiple is NM, although negative FCF and yield remain reportable. With material NCI, explain the consolidated-FCF/common-equity scope mismatch; exclude from peer ranking if reliable attribution is unavailable. |
| EV/EBITDA | `enterprise_value` / EBITDA | Operating valuation before financing costs. EBITDA must be positive; lease and NCI scope must align. A negative EV may be shown diagnostically but excluded from cheapness rankings. |
| Debt/equity | `debt_inc_leases` / `equity_total` | Consolidated financial leverage, not total liabilities/equity. Equity must be positive. |
| Net debt/equity | `net_debt` / `equity_total` | Leverage after eligible cash. Negative values can indicate net cash if equity is positive. |
| Net debt/EBITDA | `net_debt` / EBITDA | Debt relative to operating earnings. Positive EBITDA with a negative ratio indicates net cash; EBITDA ≤ 0 means NM. |
| Current ratio | Current assets / current liabilities | Short-term liquidity; interpret in the business context. Do not calculate with a zero denominator. |
| Common ROE | `net_income_common` / average `equity_common` | Return on common shareholders' book capital. Denominator must be positive. |
| Group ROA | `net_income_group` / average `assets_total` | Accounting return on consolidated assets; not an unlevered operating return. |
| ROIC | NOPAT / average invested capital | Operating return on invested capital. Non-positive capital means NM. An excluding-goodwill view may be shown separately. |
| Dividend yield | Gross common dividends per share paid during the past twelve months / current price of that class | Separate ordinary and special dividends. Declared but unpaid or forward dividends are a separate measure. Adjust splits and depositary-receipt ratios. |
| FCF yield | FCF / `market_cap` | Cash generation relative to equity market value; may be negative. Same NCI scope limitation as P/FCF. Do not substitute FCFF/market cap. |
| Net profit margin | `net_income_group` / `revenue` | Consolidated sales-to-profit conversion. Common-shareholder profit margin is a separate optional view. |
| EBITDA margin | EBITDA / `revenue` | Operating margin before D&A, interest and tax; retain the lease-treatment basis. |
| Revenue growth | Current comparable-period revenue / prior comparable-period revenue − 1 | Identify annual, same-quarter or TTM-over-TTM periods. If the base ≤ 0, show absolute change and mark percentage growth NM. |
| Book value per share — BVPS | Common equity attributable to the class / period-end outstanding shares of that class | Use balance-sheet-date shares, not weighted-average EPS shares. Allocate equity where rights differ. |
| Graham multiple | P/E × P/B | Optional historical value filter when both inputs are positive and meaningful. A threshold of 22.5 is not a universal buying rule. |
| Asset turnover | `revenue` / average total assets | Asset-use efficiency. |
| DuPont financial leverage | Average total assets / average total equity | Use consistent consolidated scope. |
| DuPont margin × turnover | Group net margin × asset turnover | Equals group ROA. It contains after-financing net income and is not an unlevered return. |
| Group DuPont ROE | Group net margin × asset turnover × DuPont financial leverage | Equals group net income / average total equity. Do not equate it with common ROE when NCI matters. |
| FCF earnings conversion | FCF / group net income | Calculate when profit is positive; retain negative FCF. Growth Capex can depress the measure. |
| Five-year FCF earnings conversion | Sum of FCF for five aligned years / sum of group net income for those years | Not the average of annual ratios. Require positive aggregate profit and complete matched data. Label shorter available windows with the actual number of years. |
| Interest coverage | EBIT / gross interest expense | Do not substitute FX losses or total finance costs, or net interest income against expense. With zero expense report "no interest expense"; retain and explain negative EBIT. |
| Interest-rate shock sensitivity | Estimated additional annual interest / EBITDA | Additional interest = debt repricing after hedging × assumed rate increase × fraction of year affected. Show +100/+200/+300 basis-point scenarios by default. Consider maturities and fixed/floating rates; do not assume leases immediately reprice. If exposures are unavailable, do not invent a precise estimate. A full gross-borrowing repricing case may be labelled as a simplified scenario. |
| Free-float percentage | Publicly tradable shares / total outstanding shares | Identify the source and local definition. Does not alter total market capitalisation. |
| Selected-period price return | Split-adjusted ending price / beginning price − 1 | User-selected window or standard 1/3/12-month windows. Price declines do not independently prove their cause. |
| Historical multiple median | Median of meaningful multiples at the preceding five fiscal year-ends | Use each date's price and financial information then available. Five year-end observations are not the median of all trading days. With 3–4 observations label actual coverage; with fewer than 3, omit the historical comparison. |
| Deviation from historical median | Current multiple / positive historical median − 1 | Negative means below the historical median. If a positive discount is wanted, use 1 − current/median and label it accordingly. |
| Cross-source discrepancy | Ratio from source A / equivalently defined ratio from source B − 1 | Diagnostic control. Align period, price, leases and NCI first; explain differences instead of averaging incompatible ratios. |

Historical medians and deviations may be produced for other indicators only where the series is meaningful and comparable. For ROE and margins, default to percentage-point changes; relative changes from small or negative bases can mislead.

## 6. Additional useful indicators

| Indicator | Formula / definition | Required convention |
|---|---|---|
| EV/sales | Enterprise value / revenue | Positive revenue and matching business scope. |
| EV/EBIT | Enterprise value / EBIT | Retains depreciation as a cost; EBIT ≤ 0 means NM. |
| Basic and diluted EPS | Earnings attributable to the class / relevant weighted-average basic or diluted shares | Prefer reported EPS, incorporating numerator adjustments for dilution. Store both series and their bases. |
| Gross margin | (Revenue − cost of sales) / revenue | Use only where the cost classification is appropriate; do not force onto banks. |
| EBIT margin | EBIT / revenue | Operating profitability after D&A. |
| CFO margin | Standardised CFO / revenue | Operating cash generation on a consistent cash-flow basis. |
| FCF margin | Standardised FCF / revenue | Cash generation after Capex; may be negative. |
| CFO earnings conversion | Standardised CFO / group net income | Require positive profit; separates operating cash conversion from Capex effects. |
| Accrual ratio | (Group net income − standardised CFO) / average total assets | Earnings/cash divergence; not standalone evidence of manipulation. |
| Capex intensity | Capex / revenue | Cash investment requirements. |
| Quick ratio | (Unrestricted cash + liquid short-term investments + net short-term trade receivables) / current liabilities | Exclude inventory and prepayments; verify investment liquidity. |
| Cash ratio | (Unrestricted cash + liquid short-term investments) / current liabilities | Liquidity from the most readily available resources. |
| Gross debt/EBITDA | Debt including leases / EBITDA | Require positive EBITDA. Shows gross financing exposure even when net debt is low. |
| Dividend payout ratio | Common cash dividends paid during the period / net income attributable to common shareholders | Require positive earnings; explain timing and special dividends. |
| FCF dividend coverage | FCF / common cash dividends paid | Require positive dividends; explain consolidated/parent scope mismatches. |
| Revenue CAGR | (Ending annual revenue / beginning annual revenue)^(1/n) − 1 | Positive beginning/ending values and n full annual intervals. A five-year CAGR requires six annual observations. |
| Diluted EPS growth | Comparable current EPS / prior EPS − 1 | Use consistently adjusted positive EPS in both periods. Describe loss-to-profit transitions separately. |
| Operating NWC/sales | Operating NWC / revenue | Working-capital requirements; negative values can be structural. |

Optional forecast measures, only with a dated accessible consensus:

- Forward P/E: price / expected FY1 or next-twelve-month diluted EPS. Identify the forecast horizon, date, contributors and earnings basis.
- Analyst target-price gap: target price / current price − 1. Identify the target horizon and source. Do not present a one-year price target and a present-date intrinsic valuation as same-date estimates.

Do not fabricate consensus or imply unavailable paid data has been obtained.

## 7. Conditional holding-company module

Activate for an investment or diversified holding company whose economic model centres on a portfolio of equity interests. A company name containing "holding" is not sufficient; do not automatically apply this module to every operating group's parent entity. Consider the banking module for bank holding companies. NAV/SOTP is the principal holding valuation approach; consolidated P/E and P/B are supplementary.

| Indicator | Definition / calculation | Required convention |
|---|---|---|
| Attributable investment value | Investee's total equity value × holding company's economic ownership percentage | Use same-date market values for listed investments; dated, justified valuation ranges for private interests. Assess different rights and cross-holdings. |
| Gross asset value — GAV | Sum of attributable investment values + other investment assets | In this specification holding-level cash is outside GAV. Do not add it twice. |
| Common-equity NAV / SOTP | GAV + eligible holding-level cash − holding-level debt/leases − preferred claims − other separate holding liabilities − explicit valuation adjustments | Investee equity values already reflect investee debt; do not deduct consolidated group debt again. Explain central-cost present values or disposal-tax assumptions separately. |
| NAV per share | NAV attributable to common shareholders / outstanding common shares | Allocate between classes where economic rights differ. |
| NAV discount | 1 − holding market capitalisation / positive NAV | Positive means discount; negative means premium. |
| P/NAV | Holding market capitalisation / positive NAV | Complement of the discount; NAV ≤ 0 means NM. |
| Historical NAV discount | Median of comparable prior month-end discounts; mean may be shown separately | Target five years; label actual 3/1-year windows if shorter. Do not combine current prices with an unlabelled stale NAV. |
| Discount deviation | Current discount − historical reference discount | Percentage points; positive means a wider discount, not a guaranteed convergence opportunity. |
| Holding net debt/GAV | (Holding-level debt/leases − eligible holding-level cash) / GAV | Subsidiary borrowing or banking deposits are not automatically parent-company borrowing. |
| Holding cash coverage | Cash dividends actually received from investments and recurring cash income / (central cash costs + cash interest + contractual lease cash payments) | Accounting investee profits are not cash receipts. Require a positive denominator. |
| Portfolio concentration | Largest investment / GAV and top three investments / GAV | Use values attributable to the holding company. |
| Unlisted-value exposure | Attributable value of unlisted investments / GAV | Indicates valuation uncertainty and liquidity exposure. |
| NAV value change | Current NAV / comparable prior NAV − 1 | Explain distributions, acquisitions and capital movements; not automatically total shareholder return. |

If reliable NAV cannot be built, report NAV unavailable rather than inventing private-company valuations. Updating only listed holdings from a dated NAV is permissible as a partially updated estimated NAV, with the dates of unchanged components identified. Avoid double counting indirect holdings and cross-holdings.

## 8. Financial institutions and sector-specific measures

For banks and insurers, operating-company EV/EBITDA, net debt/EBITDA, generic CFO/FCF and current ratios default to `not_applicable`. Funding forms part of the business model. Do not assign neutral scores to unsuitable industrial metrics.

Conditional banking indicators:

| Indicator | Definition / calculation | Required convention |
|---|---|---|
| P/E, P/B, common ROE and group ROA | Definitions above | Use appropriate banking statements with matching ownership scope. |
| P/tangible book — P/TBV | Market capitalisation / (common equity − attributable goodwill and other intangible assets) | Positive denominator; explain differences from regulatory tangible-book definitions. |
| Net interest margin | Net interest income / average interest-earning assets | Annual period or explicitly annualised interim period. |
| Cost/income | Operating expenses / operating income | Exclude credit-loss provisions from expenses for this definition. Separate exceptional items and retain the source definition. |
| Non-performing loan ratio — NPL | Gross non-performing loans / gross customer loans | Retain applicable delinquency/default definitions; do not automatically equate them with IFRS Stage 3. |
| CET1 ratio | Eligible Common Equity Tier 1 capital / risk-weighted assets | Use reported regulatory definitions and identify transitional/fully loaded basis and applicable requirements. |

Add insurance, property/REIT, oil and gas, software or other sector metrics through a defined sector module or a user request. Do not assume a jurisdiction-specific industry measure is a universal accounting line item; retain the reported definition and reconciliation.

## 9. Optional advanced quality and risk indicators

### Piotroski F-score

Optional original annual method, primarily for non-financial companies on consistent accounting and consolidation bases. Award one point for each satisfied test, otherwise zero for a verified failed test:

1. Net income before extraordinary items / beginning total assets > 0.
2. Reported CFO / beginning total assets > 0.
3. ROA on that beginning-asset basis increased versus the prior year.
4. CFO / beginning assets exceeds ROA on the same basis.
5. Long-term debt / average total assets decreased.
6. Current ratio increased.
7. No common-equity issuance during the year.
8. Gross margin increased.
9. Sales / beginning total assets increased.

Score range: 0–9 when all tests can be evaluated. Equality does not earn an improvement point; no equity issuance earns one point. Explain the mapping from the original earnings definition to available statements. Prior-year beginning-asset tests require additional opening balance-sheet data. Do not substitute the main catalogue's average-asset ROA for the original model's beginning-asset ROA. Using standardised instead of reported CFO produces a modified F-score and must be labelled accordingly. If tests are missing, show coverage and available test results rather than a fabricated complete score. Net share-count changes alone do not prove there was no equity issuance because repurchases can offset issuance.

### Altman Z-score: original publicly listed manufacturing model

Z = 1.2X1 + 1.4X2 + 3.3X3 + 0.6X4 + 1.0X5

- X1 = (current assets − current liabilities) / total assets.
- X2 = retained earnings / total assets.
- X3 = EBIT / total assets.
- X4 = market value of equity, including preferred equity where relevant / total book liabilities.
- X5 = sales / total assets.

Use decimal ratios, year-end balance-sheet amounts and matching full-year flows. Do not apply automatically to financial institutions or every sector. Any other model variant requires its own verified identity, coefficients and applicability. The result is not a default probability or a definitive insolvency judgement. Do not turn original-sample thresholds into universal alarms.

### Optional ownership and short-position data

- Fund ownership: shares held by the reporting funds / total outstanding shares.
- Foreign ownership: shares attributable to foreign investors under the disclosed applicable definition / total outstanding shares.
- Short interest: reported outstanding short positions / free-float shares, or total outstanding shares if explicitly labelled.

Specify denominator, reporting date, delay, institutional coverage and definition. Omit unavailable measures rather than inventing ownership data.

## 10. Peer selection and comparisons

Select 3–5 economically comparable listed companies. Prioritise business model, core products/services and subsector, then operating geography, scale, customers, capital intensity, growth and regulation. Same-index membership or shared listing location is insufficient. A broad energy label does not make a producer, refinery and regulated network operator interchangeable. Compare holdings with economically similar portfolio structures and banks with suitable banks.

Include user-selected peers, but flag weak matches and distinguish them from the main comparable group. Do not fill a numerical quota with unsuitable companies. Explain each selection and material differences in period and accounting treatment.

Use the median of meaningful, consistently defined peer observations. Exclude negative-EBITDA companies from an EV/EBITDA median without deleting their broader analysis. Target at least three valid peer values for a principal benchmark; with fewer values, disclose the count and limitation. Peer discount = 1 − company multiple / positive peer median. For ROE and margins use percentage-point differences. Align TTM periods as closely as possible and disclose residual fiscal-calendar differences.

## 11. User-requested indicators

For any indicator outside the standard catalogue, establish the definition from a reliable source and record its formula, period, ownership scope, currency, accounting basis and required inputs. If there is one clear established definition, show and apply it. If materially different interpretations exist, ask the user to choose or present separately labelled variants. Never change definitions silently.

Use `missing` for absent inputs, `not_applicable` for unsuitable business models and `estimated` for explicit estimates. The language model may discover sources, map statements and explain results; final arithmetic must run through reproducible calculation code. Version indicator formulas so that the same label does not conceal different calculations within a report.

## 12. Implementation reminders

- Financial reports are discovered automatically, beginning with the official Investor Relations website; uploads remain optional.
- Definitions, periods, ownership scope and units must match before comparing or combining figures.
- Use report-derived financial amounts; maintain separate reported, normalised and estimated outputs.
- Separate common-shareholder valuation from consolidated operating analysis and holding-level NAV analysis.
- Negative earnings, negative equity and missing data must not generate misleading cheapness rankings.
- Preserve original-language evidence and identify translations, estimates and management claims.
- A single composite investment score needs a separately defined methodology; these indicator definitions do not establish one.
- Produce a clear final report with sources, calculation periods, explanations and limitations. PDF is the default download, with Word as an option.
- Keep data providers and API credentials configurable; do not select subscriptions or fabricate access credentials.

## References

The sources below support the financial framework and sourcing guidance. Application-specific conventions in this document are explicit implementation choices rather than claims that every detail is prescribed by a single global standard.

- SEC: Using EDGAR to Research Investments: https://www.sec.gov/search-filings/edgar-search-assistance/using-edgar-research-investments
- SEC: Developer Resources and Fair Access: https://www.sec.gov/about/developer-resources
- SEC: Webmaster FAQ and User-Agent Identification: https://www.sec.gov/about/webmaster-frequently-asked-questions
- Damodaran: Financial Measures and Ratios: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/definitions.html
- CFA Institute: Financial Analysis Techniques: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/financial-analysis-techniques
- IFRS Foundation: IFRS 18 Effects Analysis, including IAS 7 cash-flow classification changes: https://www.ifrs.org/content/dam/ifrs/publications/amendments/english/2024/effect-analysis-ifrs18-april2024.pdf
- Piotroski: Value Investing — Original Paper: https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf
- Altman: Z-score Model Variants: https://www.altmanzscore.com/home
