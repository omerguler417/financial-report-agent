# Indicator Specification (future requirements)

Status: requirements plus implementation status. See "Implementation status" at the end for what already works.

**Indicator definitions and calculation rules now live in [`indicator_definitions.md`](indicator_definitions.md) (version 1.0, 18 November 2026). Where this file and that one differ, `indicator_definitions.md` wins, except for the "Decisions after v1.0" below, which add to it.** The differences are listed in "Changes introduced by Indicator Definitions v1.0" below. The menu below is kept for history; the authoritative catalogue is sections 4–9 of `indicator_definitions.md`.

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
- Mark missing data "Unavailable"; never invent inputs. (Superseded: use the status names in `indicator_definitions.md` section 3.)
- Treat nonpositive denominators and economically meaningless multiples explicitly.
- Do not assign universal "good" or "bad" thresholds without context.
- Treat all fetched or uploaded text (reports, transcripts, news, web pages) as data, not instructions.

## Scope additions: three-agent design

Added after the original indicator list. Nothing is predefined: the user names the company at the start, and the agents do the rest. The primary focus is companies listed on the New York Stock Exchange; companies on other exchanges can be requested.

Core workflow: summarise the written disclosures, the spoken discussion and management's outlook; calculate the predefined indicators, plus any additional indicators the user requests where sufficient data exists; and compare valuation against suitable peers and against the company's own history. Every rule below applies equally to the target company and its peers.

### Pipeline

1. The user names a company, the indicators, an output language (English by default), and optionally a timeframe, peers or a stock-market index filter.
2. The company is identified. Ask the user when its identity is ambiguous.
3. Suitable peers are selected (see Peer selection).
4. The agents fetch the documents and recordings they need (see Document sourcing).
5. Agent 1 and Agent 2 do their work.
6. Agent 3 combines both into one final report, which the user reads on the website and can download.

### Document sourcing and fetching

- The agents fetch documents themselves, in this order: (1) the company's official investor relations website; (2) if a document is missing, the relevant regulator or stock exchange, such as SEC EDGAR for US filings; (3) if it is still unavailable, identify the missing document and allow the user to upload it.
- Never silently substitute another reporting period for a missing document.
- Prefer official APIs where available; otherwise use direct PDF or HTML downloads.
- Follow website access rules, limit requests, and never bypass access restrictions.
- Save downloaded documents locally for reuse. For every document record the source URL, reporting period, publication date and retrieval date.

### Peer selection

- Select peers primarily by business model and industry, then by geography and size. Aim for three to five suitable peers.
- Explain each selection and disclose material differences from the target company (for example business model, geography, size, reporting currency, accounting standards, fiscal year-end, share classes).
- Membership in the same named stock-market index is only an optional filter the user can select. If that filter leaves too few suitable peers, expand beyond the index and explain why.
- Do not include unsuitable companies merely to reach the target number. If no suitable peer exists, say so and compare the company with its own history only.
- If the user names a peer directly, include it and disclose its material differences.
- Run the same selected indicators on each peer over the same periods. Do not produce rankings or market-wide screening lists.

### Valuation comparison

- Compare each named multiple with the company's own historical median and with its peers.
- Describe premiums and discounts together with their limitations (for example differences in business model, growth, accounting, one-off items, cyclicality, and the judgement involved in choosing peers). A higher multiple alone is not proof of overvaluation; do not label a company "overvalued" as a verdict, and do not use universal good or bad thresholds.

### Timeframes

- Default for each company: up to five completed fiscal years plus the latest available TTM data when appropriate.
- A timeframe given by the user replaces the default. If fewer comparable periods exist, say so.

### User-added indicators

- The user may name indicators beyond the menu above. Python calculates them where sufficient data exists.
- Confirm the formula and inputs with the user first; otherwise mark the indicator "Unavailable".

### Earnings calls, recordings and transcripts (Agent 2)

- Process available earnings-call recordings, presentations and interviews (audio or video), including recordings the user supplies.
- Prefer an official written transcript when one exists. If none exists, transcribe the recording.
- Support recordings in any language, and translate the transcript into the user's requested output language.
- Keep the original-language transcript alongside the translation. Include timestamps and identify speakers where possible.
- Clearly distinguish official transcripts from machine-generated transcripts and translations. Mark unclear passages and uncertain speaker identities rather than guessing.
- Check important financial figures, percentages, currencies, dates and guidance against the company's published documents where available. If the recording and a written report differ, disclose the discrepancy rather than silently changing either source.
- Cite timestamps for every claim drawn from a recording.
- Include the spoken discussion and the Q&A. Distinguish management's statements from analysts' questions and assumptions.
- Quote forward-looking statements and guidance with their location (page or timestamp), present them as management's claims, and say so when none were given.
- If a recording cannot be accessed or processed, explain the specific limitation, request an upload or another format where useful, and continue with the available material.

### News (Agent 2)

- Prioritise news published since the latest financial-results announcement, and include older developments that remain materially relevant (changed 18 November 2026).
- Sources: company announcements for official disclosures and credible independent reporting. The news provider will be selected during API setup ("Reuters preferred" was removed on 18 November 2026). For every item include the publisher, publication date and link.
- Distinguish management statements from independent reporting.
- Unusual or relevant events are controversies, political or cultural events that may affect the company specifically or its relevant index, and new regulations. Also include other recent news about the company in that period.
- Make no claim about whether news is already reflected in the share price. Do not claim that news caused a share-price movement solely because their timing overlaps.

### Market data

- Use one consistent market-data provider through a supported, permitted access method. The provider is not chosen yet and stays configurable. (Yahoo Finance was allowed earlier, but its robots.txt forbids automated access.)
- For every price record the ticker, exchange, currency, source and price timestamp, and flag stale data.
- Use the relevant closing price for dated valuations. Price returns use split-adjusted prices without dividend reinvestment; total shareholder return needs a separate dividend-reinvested series (changed by v1.0).
- Calculate historical valuation multiples using the financial information available at each historical date, avoiding hindsight (this relies on the publication dates recorded for each document).

### Language and translation checks

- No written-only or English-only restriction. Use the available tools to handle supported formats and languages. Output is in the user's requested language (English by default).
- Apply translation checks to both written documents and recordings.
- Preserve the original source and label translated content. Keep the original passage for reference.
- Check figures, percentages, currencies, units, dates, negative signs and financial terminology against the original.
- Preserve the strength of management's wording; for example, do not translate "may" as "will". Flag ambiguous wording.
- A second AI review may help identify errors but must not be described as independent verification.

### Evidence and verifiability

- Every material factual claim must have an identifiable source and a precise supporting location, such as a page, section, table or timestamp.
- Every calculated indicator must show its definition, formula, source inputs, reporting periods and units.
- Search snippets alone are insufficient evidence.
- Label unsupported information as unverified, and report missing inputs rather than inventing values.
- This is the standard behind the README's verifiable-source success test.

### Final report (Agent 3)

- Agent 3 combines Agent 1 and Agent 2 into a single final report. The user reads it on the website.
- PDF is the default download format. Word is an optional editable export containing the same analysis, tables, calculations and references.
- Every figure comes from Agent 1's Python results. Agent 3 never calculates.
- Label which agent each statement came from and show where the agents agree and disagree.

## Changes introduced by Indicator Definitions v1.0

Recorded 18 November 2026. Documentation only: no code has been changed yet. Each item says what changed relative to this file or to earlier decisions.

### Resolved open definitions

- Free cash flow: `fcf_reported` (reported CFO − Capex) and `fcf_standardised` (after cash interest and lease principal); comparisons use `fcf_standardised`.
- Enterprise value: market cap + debt including leases + preferred capital + NCI − eligible cash; separate `operating_ev` view.
- Net debt: debt **including** leases − unrestricted cash; an excluding-leases view is kept; negative means net cash. (Earlier provisional choice excluded leases.)
- NOPAT: EBIT × (1 − suitable operating tax rate); no universal tax rate.
- Invested capital: consolidated equity (incl. NCI) + debt incl. leases − eligible cash − non-operating financial investments; goodwill included.
- Leases, NCI, preferred shares and restricted cash: treated as in section 4 of the definitions; restricted cash excluded from eligible cash.
- Share count: shares outstanding near the valuation date excluding treasury shares for market cap; weighted-average basic and diluted shares for EPS; both stored.
- Price and currency: latest completed session's close; market cap translated into the reporting currency at the valuation-date spot rate. (Earlier: mark Unavailable when currencies differ.)
- TTM: four non-overlapping quarters, or last fiscal year + current YTD − prior YTD; balances are never summed.
- Averages: opening and closing balances of the same twelve months; no invented averages; closing-balance approximations labelled.
- History: target five completed fiscal years plus TTM; historical multiple median uses the preceding five fiscal year-ends with information then available; 3–4 observations labelled, fewer than 3 omitted. (Earlier: prices on each report's publication date, minimum 3.)
- Source conflicts: an official amended or restated filing takes precedence over an older copy; retrieval order never overrides document authority.
- Sector exceptions: holding-company module (section 7) and banking module (section 8) activated by economic business model, not by name.

### Changed conventions

- Statuses become `calculated`, `reported_only`, `estimated`, `missing`, `not_applicable`, `not_meaningful` (NM), `not_comparable`, replacing "Unavailable / Not applicable / Not meaningful".
- Ownership scope: P/E and common ROE use `net_income_common`; P/B uses `equity_common`; ROA, margins and DuPont use group figures; debt/equity uses `equity_total`.
- DuPont: group DuPont ROE is separate from common ROE; "equity multiplier" is renamed "DuPont financial leverage".
- Interest coverage: EBIT / gross interest expense.
- Interest-rate scenario: additional interest / EBITDA with default +100, +200 and +300 basis-point scenarios. (Earlier: coverage after one user-chosen increase.)
- Dividend yield: gross common dividends per share paid in the past twelve months / current price; special dividends separate. (Earlier: latest fiscal year.)
- Cash conversion: FCF / group net income, and a five-year version as a ratio of sums.
- Deviation from historical median: current / median − 1 (negative = below). Peer discount: 1 − company / peer median (positive = discount). ROE and margins compared in percentage points.
- Peers: exclude negative-EBITDA companies from an EV/EBITDA median; target at least three valid peer values; user-selected weak matches stay but are kept apart from the main comparable group.
- User-requested indicators: if one clear established definition exists, show and apply it; ask the user only when materially different interpretations exist. (Earlier: always confirm the formula first.)
- Every input and output carries full provenance (scope, accounting framework, restatement status, definition version); the analysis date is saved and historical as-of analyses exclude later documents.
- Display rounding: two decimal places for multiples and percentages; never round intermediate values.

### New indicators

- Core: BVPS, DuPont margin × turnover, five-year FCF earnings conversion, selected-period price return (1/3/12-month windows), cross-source discrepancy.
- Additional: EV/sales, EV/EBIT, basic and diluted EPS, gross margin, EBIT margin, CFO margin, FCF margin, CFO earnings conversion, accrual ratio, Capex intensity, quick ratio, cash ratio, gross debt/EBITDA, FCF dividend coverage, revenue CAGR, diluted EPS growth, operating NWC/sales.
- Optional with a dated consensus only: forward P/E, analyst target-price gap.
- Holding-company module: attributable investment value, GAV, NAV/SOTP, NAV per share, NAV discount, P/NAV, historical NAV discount, discount deviation, holding net debt/GAV, holding cash coverage, portfolio concentration, unlisted-value exposure, NAV value change.
- Banking module: P/TBV, net interest margin, cost/income, NPL ratio, CET1 ratio.
- Optional quality and risk: Piotroski F-score, Altman Z-score (original manufacturing model), fund/foreign ownership, short interest.

### Sourcing and Agent 2

- Identity resolution includes the share class and, where available, the CIK; confirm the document concerns the selected entity, not a similarly named subsidiary.
- SEC EDGAR: inspect 6-K contents before treating one as a quarterly report. Identification header built from configuration: `User-Agent: <SEC_APP_NAME> <SEC_CONTACT_EMAIL>`; the contact is stored only in the local `.env` (contact identification only). Fair-access maximum is 10 requests per second in aggregate; the project's 1 request per second per host is within it.
- Reputable data services may be used for cross-checking, labelled, and never silently replace report-derived figures.
- Earnings calls: reputable transcript providers may be used when no official transcript exists.
- News relevance is wider: subsector, operating locations, customer markets, supply chain, commodities, financing, regulation and sanctions; each item states its plausible business transmission channel. The news provider will be chosen when the integrations are configured.
- Providers and credentials stay configurable; no subscription is selected and no credentials are fabricated.

### Decisions after v1.0 (18 November 2026)

- **Earnings yield (kept).** TTM net income attributable to common shareholders / market capitalisation.
- **Average daily trading volume and average daily traded value (kept).** Latest 60 completed trading sessions by default (`TRADING_WINDOW_SESSIONS`, configurable). Disclose the actual number of sessions covered, and label traded-value approximations (for example close × volume instead of reported turnover).
- **News.** "Reuters preferred" removed; the news provider is selected during API setup. Prioritise news since the latest financial-results announcement, and include older developments that remain materially relevant.
- **Peer selection order (confirmed).** Business model, products/services and subsector first; then geography, scale, customers, capital intensity, growth and regulation. Explain each selection and its material differences.
- **Optional modules.** Deferred; do not expand the implementation scope for them.
- **Fiscal years.** Use each company's actual fiscal calendar and exact reporting dates. Calculate TTM from non-overlapping periods. Clearly identify shortened or extended reporting periods, avoid misleading growth comparisons, and never annualise automatically.
- **Providers.** Providers and API credentials stay configurable and are chosen later. The application must clearly distinguish working integrations, integrations awaiting configuration, and demo data.
- **EDGAR contact.** Stored only in the local `.env` as `SEC_CONTACT_EMAIL` (loaded automatically at start-up); `.env.example` holds a placeholder; the User-Agent is built from configuration (`SEC_APP_NAME` + `SEC_CONTACT_EMAIL`).

### Decisions for step 3: indicator calculations (22 November 2026)

- **Core set built first.** P/E, P/S, P/B, P/FCF, EV/EBITDA, FCF yield; debt/equity, net debt/equity, net debt/EBITDA, current ratio, interest coverage; common ROE, group ROA, ROIC, net profit margin, EBITDA margin; revenue growth, FCF earnings conversion, five-year FCF earnings conversion; book value per share. The rest of v1.0 sections 5–8 comes later.
- **ROIC tax rate.** NOPAT = EBIT × (1 − the statutory tax rate of the company's home country). The rate is taken from the company's own report (tax note), cited with document and page; it is never borrowed from another year. For US companies this is the 21% federal statutory rate, with state taxes excluded. If the report does not state the rate, ROIC is `missing`. No tax benefit is assumed on an operating loss.
- **FCF.** Until cash interest paid and lease principal are extracted, comparative FCF is reported FCF (CFO − capex), labelled as such (v1.0 permits this fallback).
- **Enterprise value.** NCI at book value, disclosed as a proxy. Preferred capital is added at book value when the balance sheet shows it; when it shows no preferred line, none is added and the note says so.
- **Price.** The closing price of the latest completed trading session on or before the analysis date.
- **Banks and insurers (decided 22 November 2026).** `not_applicable`: EV/EBITDA, net debt/EBITDA, current ratio, P/FCF, FCF yield, both FCF conversions, EBITDA margin, ROIC, debt/equity, net debt/equity and interest coverage. Funding is part of their business model (v1.0 section 8); the report says why for each one. P/E, P/S, P/B, common ROE, group ROA, net margin, revenue growth and book value per share are still calculated.
- **History and peers.** Indicators that need no share price are also calculated for each fiscal year. Multiples at past year ends (historical multiple medians) come later. Peer medians use only `calculated` values and say how many there are. Multiples are compared as a peer discount (1 − company ÷ peer median); ROE, ROA, ROIC and margins as percentage-point differences; book value per share is not compared across companies.
- **Demo data.** Each demo annual report has a tax note stating the fictional 21% statutory rate. A prior-year Q3 report is added so its balance sheet can open the trailing-twelve-month averages.

### Decisions for step 4: agents and pipeline (22 November 2026)

- **Built in two parts.** 4a: pipeline, Agent 1, checks and API endpoints. 4b: Agent 2 and Agent 3.
- **No general "ask" function for live text models yet.** The existing optional adapter can still only transcribe and translate. A live analysis reports that the text model "cannot yet run the analysis tasks" (HTTP 424) until a provider is chosen and its adapter gets that part. Demo mode uses recorded answers.
- **Providers wait for the API stage (decided 22 November 2026).** No provider is chosen or paid for now. The professor will supply the providers and API keys at the API stage; each then gets its adapter (text model with the analysis tasks, market data, news, speech-to-text). Using the Claude API as the text model was considered and deferred to that stage.
- **Text model and speech-to-text: OpenAI (decided 25 November 2026).** The professor supplied an OpenAI API key; it is stored only in the local `.env` (`LLM_API_KEY`, `TRANSCRIPTION_API_KEY`), never in tracked files. Both services use the existing optional `openai_compatible` adapter with `https://api.openai.com/v1`. A free check confirmed the key works. This is the group's explicit choice, not a default; the provider stays configurable.
- **Text model: `gpt-5.4-mini` (decided 25 November 2026)** for building and testing; a larger model may be chosen for the final run by changing `TEXT_MODEL` only. Not yet tried with a real request: the agents need the analysis-task ("ask") part of the adapter first, and one tiny test request needs the group's approval because it uses the professor's credit.
- **Speech-to-text model: not chosen yet.** `whisper-1` is suggested because the adapter asks for segment timestamps (needed to cite calls by timestamp); the newer `gpt-4o-transcribe` models may return text without timestamps.
- **One switch point for demo mode.** `backend/pipeline.py` loads `backend/demo/` only when the user picks demo mode for the analysis. A live analysis first checks every service it needs and lists all that are not ready (HTTP 424), including report discovery, which is not built yet. It never falls back to demo data.
- **Checks before anything is used (`backend/validation.py`).** A figure the model extracts is used only if its line is on the page it cites and the value matches; otherwise it is rejected with the reason. Two documents giving different values for the same figure and period are both left out until precedence is clear. A model statement must cite a document page or a calculated result. Any number in it must appear in that source or match that result, otherwise it is labelled "unverified" (kept, not dropped).
- **Company identification.** An exact ticker wins; one match is used; several matches are returned to the user to choose from (HTTP 409); no match gives HTTP 404.
- **Analysis date.** Saved with each analysis; reports published after it are left out and listed in the notes.
- **Business model.** Bank or insurer treatment is taken from the industry classification, never from the company's name.
- **Demo answers.** Recorded in `backend/demo/demo_answers.py`. Four contain deliberate mistakes so the checks can be seen working: a figure cited to the wrong page and a growth rate that differs from Python's (Agent 1), a news assessment claiming the news moved the share price (Agent 2), and a valuation verdict (Agent 3).
- **Agent 2 (step 4b).** Earnings-call statements are typed as management, guidance or analyst; the speaker must appear on the cited page. News: items since the latest results announcement (the newest report's publication date), plus older items only when judged still material; items after the analysis date are left out. Publisher, date and link come from the news source, never from the model; irrelevant items are listed with the reason.
- **Agent 3 (step 4b).** Overview, disagreements (each position says who said it) and risks come from the model and are checked like every other statement. Each statement is labelled with what it rests on (Agent 1 reports, Agent 1 calculated, Agent 2 earnings call, Agent 2 news), derived from its citations. Missing information, unverified statements and limitations are built in Python.
- **Wording checks (all agents).** (Changed 28 November 2026: "expensive" and "cheap" are now allowed beside a named benchmark; see "Relative valuation language".) A statement that gives a valuation verdict or recommendation (for example "expensive", "undervalued", "should buy") or links news to a share-price move is labelled unverified with the reason.

### Decisions for step 5: the website and downloads (22 November 2026)

- **Built in two parts.** 5a: run an analysis on the website and read the report. 5b: PDF (default) and Word downloads.
- **One shared layout (`backend/report_blocks.py`).** The finished report is turned into display blocks in a fixed order: overview, disagreements, key figures (with peer medians and the sources of every figure), key figures by fiscal year, what the reports say, earnings call, news, risks, not verified, missing information, limitations. The website draws these blocks; the PDF and Word files will draw the same ones, so all three match.
- **Demo mode is a tick box the user chooses for each analysis** (unticked by default). A demo report shows the DEMO label first and last; unverified statements are highlighted with their reasons.
- **Downloads (step 5b, 25 November 2026).** "Download PDF" and "Download Word" at the end of the report. Both files are drawn from the same display blocks as the website. A demo report carries the DEMO label in the header of every page, and the file name ends in `_DEMO`. PDF uses reportlab 5.1.1; Word uses python-docx 1.2.0. The PDF's built-in fonts cover Western European text; a few signs (−, →, ≤, ≥) are swapped for plain equivalents.
- **Libraries pinned.** pypdf 7.0.1, python-docx 1.2.0 and openpyxl 3.1.5 (used since step 2) and reportlab 5.1.1 are now pinned in `requirements.txt`; the step 2 libraries had been installed locally but never pinned. A fresh install from `requirements.txt` passes all tests.

### Decisions for the folio. website design (25 November 2026, branch `v3-frontend`)

- **New look, same functions.** The website follows the folio. v3 description: navy sidebar with six pages (New analysis, Agent workflow, Analysis dashboard, Sources & transcripts, My reports, Services & setup), white cards, green accent, blue for Agent 1, green for Agent 2, purple for Agent 3. Built on the existing endpoints; no backend behaviour changed.
- **Fields the backend does not use yet** (horizon, choosing indicators, extra questions) are shown disabled and labelled "Coming later". Uploads in the form work but are labelled as not yet used in the analysis.
- **My reports** remembers analyses in the user's browser only; a list kept on the server would need a new endpoint (open).
- **Live is the default data choice**; demo is the user's explicit choice for the whole analysis.
- **No figures are calculated in the browser.** Cards and tables show the values Python formatted (`/view`); the chart plots Python's values and only works out drawing positions. Before an analysis has run, pages show empty states, never sample figures. Nothing is loaded from outside the project (system fonts; Inter only if installed).
- **FFmpeg setup text** now says it is only needed for uploaded recordings and gives the Mac and Windows install commands, instead of "add to .env".

### Decisions for the remaining v1.0 indicators (25 November 2026, branch `v3-frontend`)

- **Deadline moved to 1 December 2026.**
- **Scope.** Add the rest of v1.0 section 5 and all of section 6 (part B), the bank module of section 8 (part C) and the holding module of section 7 (part D), each approved and checked in turn. Not included: the optional section 9 modules (deferred by `CLAUDE.md`) and the two forward measures (they need a dated consensus source).
- **Dropped by decision:** the interest-rate shock sensitivity and the cross-source discrepancy (no second data source). They are not calculated or shown.
- **Free cash flow.** Comparisons use v1.0's standardised FCF (standardised CFO − capex; standardised CFO is after cash interest and lease principal). The reported figure (CFO − capex) is kept alongside. Where the adjustments are not in the inputs, reported FCF is used and labelled, as v1.0 allows.
- **Historical multiple medians.** Calculated at the preceding fiscal year-ends from the price and the reports published by each date. The demo gets the past Q3 reports this needs.
- **Demo holding company (part D).** A fictional `.DEMO` company, labelled like the other demo data, used only in demo analyses and never mixed with live data.
- **Choosing indicators.** The New analysis form lists every indicator by group; the user can untick groups or single indicators (all ticked by default). The report, PDF and Word show only the chosen ones and list what was left out.

### Decisions for live analyses from SEC EDGAR (25 November 2026, branch `v3-frontend`)

- **Figures from EDGAR's XBRL data.** For SEC filers, report figures come from the SEC's structured data (`data.sec.gov` company facts), not from a model reading PDFs. The SEC tag of each figure is mapped to a v1.0 field; values are converted to millions (shares to millions of shares) in Python. Filings published after the analysis date are left out; a restated figure uses the latest filing and notes the earlier value.
- **Citations at section level.** An EDGAR figure cites the filing (form, period, filing date, link), the statement and the SEC tag instead of a page number. `CLAUDE.md` allows "document + page + table or section".
- **Text parts use `gpt-5.4-mini`** through the "ask" part of the `openai_compatible` adapter: Agent 1's summary (from the latest 10-K and 10-Q, read into pages), Agent 2's analysis of an uploaded call transcript, Agent 3's combined report. Every answer is checked as before.
- **Live runs without share prices and news (decision c).** A live analysis runs when the text model and SEC identification are configured. Without a market-data provider, price-based indicators and peers are not available and say so; without a news provider, the news section says so. Nothing is filled with demo data. This replaces the earlier rule that a live analysis stops (HTTP 424) when any service is missing.
- **D&A built from two SEC figures (decided 25 November 2026).** When a filer reports no combined D&A figure (for example Microsoft), D&A = `Depreciation` + `AmortizationOfIntangibleAssets`, labelled with both tags; finance-lease amortisation is not added, to avoid double counting.
- **Interest paid under US GAAP (decided 25 November 2026).** For 10-K/10-Q filers (US GAAP), interest paid is classified within operating cash flow (ASC 230), so standardised CFO/FCF needs no interest adjustment even when the amount is disclosed only annually; the note says so.
- **Market data: Twelve Data, with a recorded robots.txt exception (decided 25 November 2026, awaiting the professor's acknowledgment).** The key works, but `https://api.twelvedata.com/robots.txt` says `User-agent: * / Disallow: /`. Twelve Data's terms of use (last updated 1 January 2026) license "the Platform", defined to include "the APIs (REST and WebSocket)", for "Internal Use" (sections 1, 2.1), and do not forbid automated API access beyond exceeding rate limits (2.3h). The group therefore added a narrow exception to `CLAUDE.md` for `api.twelvedata.com` only; conditions: own key, rate limits respected, no commercial use of free-tier data (2.3l), no redistribution or public display of its data (2.2e). One test request (1 credit) was sent before the robots.txt result was acted on, by mistake. Full explanation: `docs/twelvedata_robots_exception.md`. If the professor does not agree, the fallback is Tiingo, whose robots.txt allows its API.
- **Automatic peers from EDGAR (decided 25 November 2026).** Candidates are listed SEC filers with the target's industry code (SIC), from the SEC's company list by industry, ranked by closeness of annual revenue (the SEC's cross-company "frames" data, latest complete calendar year). Because EDGAR has no products, customers or regions, a candidate with no business information but the same industry code is kept as a peer with limited comparability, labelled "selected (matched on SEC industry code and size only)", and its explanation says so. Companies with business information follow the full v1.0 rule. If the peer search fails, the analysis continues without peers and says why.
- **Twelve Data's pace.** Requests to `api.twelvedata.com` are spaced 7.5 seconds apart (`MARKET_DATA_MIN_INTERVAL_SECONDS`) to stay within its free plan's 8 requests a minute; peers' reports are not downloaded, only their figures and prices.
- **The horizon (decided 27 November 2026; definitions v1.1).** The user chooses 3, 5 (default) or 10 fiscal years of history in the New analysis form (`horizon_years` in `POST /api/analyses`; any other value is refused). The horizon also sets the window of the multi-year measures: revenue CAGR over n years (n + 1 annual figures), multi-year FCF earnings conversion (shown as "Three-year", "Five-year" or "Ten-year", or by the years actually used when fewer exist, for example "7-year"; its id `fcf_conversion_5y` is kept so saved reports still open) and the historical multiple medians (n preceding year ends). EDGAR figures are kept for n + 1 fiscal years; Twelve Data is asked once per company for 11 years of closes, enough for any horizon, so a longer horizon costs no extra credits. With fewer years than chosen, the actual coverage is labelled. The demo data has five years, so a 10-year demo shows that label. The report header states the horizon.
- **Filling gaps in the SEC data (decided 27 November 2026).** A live Microsoft run showed only 2 of 5 peers with valuation values and none with EV values, because companies tag the same figure differently. Fixes: (1) bug: a sum of tags (leases, debt) now uses, for each period, the tags that period's report uses (Adobe and Block tag the lease total only in annual reports), and a tag with value 0 does not hide another that has the figure; (2) Oracle's debt: `LongTermNotesAndLoans` + `NotesPayableCurrent` added as a third way to read debt; (3) **shares outstanding: when the balance sheet gives no count, the count on the same report's cover page (`dei:EntityCommonStockSharesOutstanding`) is used**, labelled with its date (v1.0: "shares outstanding near the valuation date"); companies that report the count by share class only (for example Block) get no market capitalisation, and the notes say why; (4) **minority interests: a report without a `MinorityInterest` figure counts as none for that period**, with a note (extends the earlier rule for filers that never report it; Salesforce stopped in 2011); (5) **dividend yield: when no dividends per share paid are reported (Microsoft and Salesforce report declared amounts), cash dividends paid to common shareholders ÷ shares outstanding is used, with status `estimated`**; declared amounts are not used (v1.0 calls them a separate measure); (6) **peer comparisons: every percentage measure gets the percentage-point difference from the peer median** (definitions v1.1); (7) notes say why a value is missing when the source never has it (free float: the SEC data has no free-float share count) and, for an omitted historical median, what was missing at each year end (Microsoft's quarterly reports before 2025 have no standard depreciation tag); (8) the statement checker no longer reads "Agent 1" as the number 1.
- **Comparison lines and a clearer dashboard (approved 27 November 2026).** Python writes short lines from the calculated results (`backend/comparisons.py`), never the text model: the company against the peer median (relative difference for multiples, percentage points for percentages, with the peer count when below three or below the full set), against its own historical median, its historical medians against each peer's own, and the trend over the horizon ("higher"/"lower", never "rose"/"fell", which the wording check reserves for share-price claims). Each group of indicators gets a summary (how many measures are above or below the peer median, then its key indicators). Lines pass the same wording check as model statements, cite the results they come from, are computed from saved results (older reports get them too) and appear on the dashboard and in the report, PDF and Word. Each peer's own value is now kept in the peer comparison (`peer_values`). Dashboard plan: topic cards with compact tables, details on click, footnote numbers with one expandable sources box per card, calmer "Unverified". Built (27 November 2026): explanations below each table in one panel ("Against the peers", "Against its own history", "Over time"); statements as plain reading text instead of boxes; Agent 1's report statements carry a topic (business, results, outlook, risks) and are shown under those headings; the Overview tab adds "What the numbers show" (each group's lead comparison); metric cards show the peer median and difference. The statement checker ignores an empty placeholder citation (no document, no indicator) copied from the answer format; a statement still needs at least one real citation.
- **A company's own XBRL element when the standard figure is missing (decided 27 November 2026, option 1).** Microsoft's 10-Qs before 2025 report D&A only under its own element `msft:DepreciationAmortizationAndOther` ("depreciation, amortization, and other"), which the SEC's summary data omits, so EV/EBITDA could not be built at past year ends. Now, for each twelve-month set the analysis adds up (the current one and one per past year end) in which a standard D&A figure is missing, Agent 1 reads the company's own D&A element for all three periods from their full filings on sec.gov (the 10-Q also gives the year-earlier period, as published then; totals only, no dimensions, exact period dates). It is stored as a separate field and used only when it covers the whole period: standard and own figures are never mixed in one sum. Each figure cites its filing and element, and says when the element includes "other" items and is therefore broader; a historical median says which year ends use it. Checked on Microsoft's real filings: FY2024 = 22,287 million, as in its annual report; about 19 seconds and 9 filings more per run, free.
- **EV/sales and EV/EBIT are also compared with their own history (decided 27 November 2026, option B),** like P/E, P/S, P/B, EV/EBITDA and P/FCF (v1.0 section 5 allows other historical medians where the series is meaningful): 63 indicators in total. Microsoft, 27 November 2026: EV/EBITDA 24.94x, EV/sales 13.60x, EV/EBIT 30.25x as 5-year medians (4 year ends).
- **Calculated figures quoted without their citation (decided 28 November 2026).** When a statement quotes a number that is exactly one of this analysis's calculated results for the current period or a peer median, as Python formats it (two decimals, with its % or x), and the cited pages do not contain it, the checker attaches that result as the statement's citation instead of marking it unverified. A rounded figure, a figure from another period, or any number that is in neither the cited pages nor the results still makes the statement unverified. Checked on the latest Microsoft run: the one unverified overview point had six such figures (P/E, EV/sales, P/FCF, net margin, gross margin, revenue growth), all matched, so it would be verified.
- **No agent labels on the dashboard and in the report (decided 28 November 2026).** Cards and statements no longer carry "Agent 1 · calculated in Python" or "Based on Agent 1 (reports) · Agent 2 (earnings call)"; the Agent workflow page still shows the agents. The models are told that a sentence quoting a calculated indicator must cite it, and that overview points are one or two sentences each (a real run's single long overview point quoted P/E and EV/sales but cited only the reports, so it was correctly marked unverified).
- **Relative valuation language (decided 28 November 2026; CLAUDE.md §5 changed).** The report may call the shares expensive, cheap or (broadly) fairly priced when the same sentence names the benchmark: "relative to its peers", "against its own 5-year history", "compared with the peer median". A verdict with no benchmark ("the shares are cheap"), calling a company over- or undervalued, buy/sell/hold, ratings, "we recommend" and price targets stay forbidden. `validation.wording_issues` enforces this sentence by sentence.
- **Valuation summary (decided 28 November 2026).** The last report section, before the appendices. Python decides it: P/E, EV/EBITDA, EV/sales, P/B and P/FCF, each against the peer median and, separately, against the company's own historical median. A multiple more than 15% above its benchmark counts as above, more than 15% below as below, otherwise in line (±15% band). If more than half of the compared multiples are above, the label is expensive; more than half below, cheap; otherwise broadly fairly priced. At least two multiples are needed per benchmark; negative multiples are not compared. The section shows the overall sentence, a table of each multiple, the Python sentence per benchmark, Agent 3's explanation, and the note "This sums up the comparisons in this report. It is not investment advice."
- **Section commentary (decided 28 November 2026).** Agent 3 (task `write_commentary`) writes, for each comparison section, a headline and a two-to-four-sentence paragraph in the style of a bank's research note, explaining what the comparisons could indicate (always as possibilities), and two or three sentences explaining the valuation summary. The Python comparison lines are shown to the checker as one page per section, so a sentence may quote their numbers; its citation is then replaced by the calculated results those lines were built from. Only verified sentences are shown in the panels and the report; unverified ones are listed in Appendix D. A section without verified commentary, or a report saved before 28 November 2026, shows the Python lines as before. On the website the headline replaces "What the comparison shows" and the Python lines open under "The comparisons in detail".
- **Call speakers (decided 28 November 2026).** The checker matches a speaker by name, since the model shortens titles ("CEO" for "Chief Executive Officer"). What is shown comes from the transcript: company speakers with the official title of the cited turn, analysts by name only.
- **Only real disagreements (decided 28 November 2026).** A disagreement whose positions all come from one source (or cite none) is left out; the Overview card appears only when two different sources conflict, and the report says "No disagreements were identified." otherwise. In six Microsoft runs, one had real disagreements, three had only same-source items.
- **What the reports say, laid out like a research note (decided 28 November 2026).** Business and outlook side by side as short paragraphs; results as one explained paragraph per period, the periods one under the other (the model gives each result its period and writes it as explanation, not a list of figures); risks as numbered cards on the Financials & peers tab, each with a two-to-four-word title from the model (the Overview keeps its plain list of Agent 3's risks, which the user preferred). A risk's title goes through the same wording check as its sentence.
- **Footnotes in the report (decided 28 November 2026).** In the report tab, PDF and Word, a point or commentary paragraph no longer has a source line under it: it ends with superscript footnote numbers, and each section ends with its sources in one line of small print (numbered from 1 in each section; a source cited by several points gets one number). Notes use short document names ("10-Q, quarter ended Sep 2026, p. 28", "Q1 FY2027 earnings call, turn 3"); the full titles stay in Appendix C. The calculated results a section cites share one note: "Company filings and market prices, TTM to Q1 2027; calculations in Appendix A, sources in Appendix C." Report-style wording throughout, never "our calculations": exhibit tables say "Source: Company filings, Twelve Data, Verity."
- **Executive summary picks what matters (decided 28 November 2026).** Agent 3 no longer lists indicators one after another (a live run had two overview points quoting twenty ratios). It quotes a calculated indicator only when it tells the reader something (a large gap to the peers or to the company's own history, an unusual level, a clear change) and says in the same sentence what it means; there is no fixed number. Every ratio stays in the report's exhibits, the valuation summary table and Appendices A and B.
- **Fixes from a live Coca-Cola run (28 November 2026).** (1) The call's fiscal quarter counts elapsed days, not calendar months: 52/53-week quarters end a few days into a month (KO's Q3 ended 2 October and was asked for as Q4, so no call was found). (2) A commentary sentence that cites a calculated result without its period gets the period the section's comparison lines used (results such as "FY2025 vs FY2024" or a dated price window are not labelled with the current period). (3) The warning that only US market holidays are known now follows the exchange the share prices came from; SEC search leaves the company's exchange empty, so every report had carried it. (4) Twelve Data gets share-class tickers with a dot (BF.B for SEC's BF-B). (5) The valuation commentary explains the summary instead of repeating its sentences.
- **Debt reported together with finance leases (decided 28 November 2026).** For a period without the usual debt tags, debt is taken from LongTermDebtAndCapitalLeaseObligations (+ its current part, or the IncludingCurrentMaturities total) plus one of NotesAndLoansPayable, CommercialPaper or ShortTermBorrowings (one only, since notes and loans payable include commercial paper). When the finance-lease liability is tagged it is subtracted, so leases are counted once, in lease_liabilities; when it is not tagged, nothing is subtracted, the note says the figure includes finance leases, and lease_liabilities then holds operating leases only. Coca-Cola: about USD 41.6bn at the Q3 2026 balance sheet; before, its debt and every EV multiple were missing.
- **Above or below must match the numbers (decided 28 November 2026).** When a sentence quotes a calculated figure and its peer median or its own historical median (as Python shows them, with two decimals) and says only "above / higher / premium / ahead of" or only "below / lower / discount / trails", Python compares the two and marks the statement unverified if the direction is wrong. A sentence using both directions is left alone. Found in a live Coca-Cola run: "valuation ratios above peer medians, including P/E at 28.64x versus 36.03x".
- **Differences from the company's own history (28 November 2026).** "P/E is 30.06% below its historical median" matches the stored -30.06% only when the same clause names the multiple and says below, and only for the company's own difference, never the peers' median of theirs. A stated difference must also point the right way: a live Apple run wrote "P/E is below its historical median by 15.91%" while it was 15.91% above, which is now marked unverified. Checked on five live reports: only the two real errors (Apple's and Coca-Cola's) are flagged.
- **Checks refined on seven live reports (28 November 2026).** The above/below check reads clause by clause; a clause without a direction word takes the previous clause's ("ratios above peer medians, including P/E at 28.64x versus 36.03x"), and "expensive"/"cheap" count as directions; only a clause that continues the previous one ("including", "with", "such as", "led by") takes its direction, never one after "while" or "but". Results of the current analysis are matched whatever their period label ("FY2026 vs FY2025" for diluted EPS growth); older years still are not. The peers' median of their own historical medians must not be presented as the company's own ("its historical median of 29.33x"); a clause that names the peers or a peer's ticker is left alone. Analysts written with their firm ("Adam Wood with Morgan Stanley") are matched and shown by name. On the seven reports every remaining flag is a real error: KO's P/E "above" peers (below), Apple's P/E "below" its median (above), Apple's FCF yield "below" peers (above), and two peers' medians presented as Apple's own; the CEO-attributed answer in turn 42 was the COO's.
- **Last checker repairs before the presentation (28 November 2026).** Format repairs, each with the numbers still checked: a citation written as text inside the indicator field ("{'indicator': 'pe', 'period': 'FY2026'}") is read as an object; a citation without a period, or with "FY2026" for a result labelled "FY2026 vs FY2025", finds the current result even when the history lists it too; an analyst written with a short first name ("Ben" for "Benjamin Reitzes") is matched by surname and shown as the transcript spells it; "versus its past" and "its trading range" count as benchmarks. The model is told that a 'peer median' figure is never the company's own. Final live runs: Microsoft 56 of 56 statements verified, Apple 26 of 26 (its call was missing because the free Alpha Vantage plan allows 25 requests a day).
- **Fixes from a live Apple run (28 November 2026).** A citation whose document id is an indicator id (the model wrote {"doc_id": "pe", "page": 0}) is read as a citation of that indicator; its numbers are still checked. Apple's current marketable securities (MarketableSecuritiesCurrent) count as short-term investments, so its quick ratio can be calculated. Historical medians are now taken at the company's fiscal year-ends, as docs/indicator_definitions.md requires (they were taken at 31 December): the dates come from the annual balance-sheet figures' period ends (Apple 2025-09-27, Microsoft 2025-06-30), with the price and the reports published by that date; figures read from documents, which carry no end date, still use 31 December. Microsoft's medians moved slightly (P/E 36.69x, EV/EBITDA 24.92x). Apple's EV-based history stays missing for a real reason: its 10-Qs do not tag lease liabilities, and missing is not zero. A citation left at the answer format's page 0 is a placeholder, not a citation (the statement then stands on its other sources); quoted historical medians get their citation automatically like current figures and peer medians.
- **The agent is called Verity (decided 28 November 2026).** Latin for truth, because every statement is checked against its source. The sidebar, the browser tab, the report cover, the PDF and Word header and the presentation's title slide show "Verity" with "Financial Report Analysis Agent" beside or beneath it; the top bar of every page is headed "Financial Report Analysis Agent" (the breadcrumb is removed; the page name stays in each page's heading).
- **The project's name replaces "folio." (decided 28 November 2026).** "folio." was a placeholder brand from the v3 design brief. The website (tab title, sidebar, report cover), the PDF and Word page header and the presentation now say "Financial Report Analysis Agent"; exhibit source lines say "our calculations"; the breadcrumb shows the page name only.
- **Earnings-call summary and readable appendices (decided 28 November 2026).** Agent 2 no longer lists the whole call: it gives up to 8 key management points and up to 5 guidance points, and up to 6 key analyst questions, each with who asked, the question in one sentence, who answered and a short summary of the answer. Every sentence is still checked against its cited turn, including that the named speaker appears there. The dashboard's Earnings call tab and the report show the same summary (Key points, Guidance, Questions and answers). Appendices: A has a short status instead of long notes; B shows values or a dash (reported EPS values instead of "reported only", per-share rows labelled with their currency, empty rows left out); C lists sources once per document instead of once per indicator; C to F use a smaller type.
- **Research-note opening (decided 28 November 2026).** The report's first page leads with the company name, one line (ticker, analysis date, LTM period, horizon, definitions) and a box with key comparisons on the left and key data and peers on the right, before the executive summary; section headings stay on the page of what follows them. Amounts are shown in banker style (USD 3,660.4bn). The dashboard's header becomes a navy masthead (company analysis, date, company, ticker, period, horizon, peers) and the Overview tab opens with key comparisons and key data side by side. Verified statements are listed before unverified ones, which stay visible and labelled. Rows and columns with no data are left out of the dashboard tables and exhibits; the appendices still list every indicator and what is missing.
- **Saved analyses listed from the server (decided 28 November 2026).** "My reports" now lists the finished analyses kept on the server (`GET /api/analyses`, newest first), so any browser on the computer sees them, and each can be opened, downloaded as PDF or Word, or deleted (`DELETE /api/analyses/{id}`, after a confirmation). The list that only this browser remembered is removed, and so is the old "Saved reports" list and its storage code, which nothing filled any more.
- **Feature list removed; share price check on the first page (decided 28 November 2026).** The "Feature status" list (working / awaiting implementation) is deleted from the page, the API and `CLAUDE.md`; its open items are kept under "Still open" below. The share price check moved from Services & setup to the New analysis page and takes a ticker only: it returns the last closing price (the latest completed session), so during trading hours it gives the previous session's close, never a moving price.
- **Investment-banking-style report and dashboard (approved 28 November 2026).** The report, PDF and Word follow the order of a bank's company report: key-data box (share price, market capitalisation, enterprise value, period, horizon), 1 Executive summary (with key comparisons), 2 Your questions, 3 Financial summary (Exhibit 1: revenue, EBITDA, EBIT, net income to common, operating cash flow, capex, standardised FCF by fiscal year and LTM, USD millions), 4 Trading comparables (Exhibit 2: the company, each peer and the peer median), 5 Historical valuation (Exhibit 3: current multiple, own median, difference, peers' median of own medians), 6 Financial analysis (comparison lines as short paragraphs), 7 Business overview and outlook, 8 Earnings call highlights, 9 Where the sources disagree, 10 Key risks, Appendices A–F (all indicators, by fiscal year, sources, not verified, missing information, methodology and limitations). Exhibits are numbered with a source line; the PDF has serif navy headings, a header rule and the footer "For educational purposes only. Not investment advice." There is no rating, price target, recommendation or investment thesis, and no bank's name or branding. The dashboard shows the key data, financial summary and comparables in the same style, and the grey explanation lines were removed. Exhibits are built in `backend/exhibits.py` from Agent 1's results (new: `financial_summary` and `market` in the indicators).
- **Peers need data for the valuation comparison (decided 28 November 2026).** Block (XYZ) is a listed company (NYSE); its gaps come from its two share classes, which the SEC summary data does not add up. Rule: when the company itself can be valued, a peer without a share count or a price is skipped and the next-closest suitable company takes its place (the peer selection now keeps a reserve list); user-requested peers are kept. Skipped peers are listed with the reason. Peers are already limited to listed companies (a ticker on the SEC's list).
- **Demo mode removed (decided 27 November 2026).** Live analyses work, so the Demo option, demo labels, demo banners and the DEMO label in the PDF and Word files are removed from the app; every analysis is live. The fictional sample company moved from `backend/demo/` to `tests/sample/` and is used only by the tests, through a test hook (`create_app(..., analysis_services=...)`), so the tests still run without network, keys or cost; a test checks that the app never imports it and has no demo code. `CLAUDE.md` updated: done = a live analysis runs end to end; providers named; demo rules removed; an unconfigured service returns a setup message, never sample data. Fallback for the presentation: open a saved report under "My reports" (it needs no live service).
- **The user's own questions (approved 27 November 2026).** Up to three questions of up to 300 characters, one per line in the New analysis form. Agent 3 answers them in one model call (task `answer_questions`) using only the six most relevant pages per question from the reports and the earnings call that were read (the existing keyword search) and the calculated indicators; every sentence is checked like the other statements (sources, numbers, wording). A question the sources do not answer is shown as "The reports and the call do not answer this question." The answers appear under "Your questions" on the Overview and in the report, PDF and Word. Demo mode has a recorded answer for questions about capital expenditure; other demo questions are shown as not answered.
- **News removed; Integrated assessment tab removed (decided 27 November 2026, for the presentation).** The news function is deleted from the code, not just hidden (settings, service entry, placeholder fetcher, Agent 2's news review and its prompt, the demo's news items, the report's News section and the website), so the code matches the project as presented; it may be rebuilt after the presentation. Agent 2 is now the earnings-call analyst (`backend/agents/call_analyst.py`) and Agent 3 combines Agent 1 and the call. The website's "Meetings & news" tab became "Earnings call", and the "Integrated assessment" tab was removed; disagreements, when there are any, are shown on the Overview. Unverified statements stay labelled where they appear (CLAUDE.md), and the downloadable report keeps its "Not verified", "Missing information" and "Limitations" sections. `CLAUDE.md` updated: Agent 2 analyses the earnings call; call transcripts are cited by speaker turn. The demo now has two deliberate mistakes (Agent 1's growth rate, Agent 3's verdict); its news-based one is gone.
- **Earnings-call transcripts from Alpha Vantage (decided 27 November 2026).** YouTube's API only gives captions to a video's owner, and Seeking Alpha has no public API (only paid enterprise licences; scraping is not allowed here), so the group chose Alpha Vantage's `EARNINGS_CALL_TRANSCRIPT` function with a free key (`CALL_TRANSCRIPT_PROVIDER=alpha_vantage`, `CALL_TRANSCRIPT_API_KEY`). Its robots.txt does not exist (HTTP 404), so nothing is disallowed. Agent 2 asks for the call of the company's fiscal quarter of the latest report Agent 1 used (Microsoft's quarter to 30 September 2026 is "2027Q1"), once per analysis, peers excluded; each speaker turn becomes a citable section ("turn 7"); the provider's sentiment score is not used. An uploaded transcript comes first and then no request is made. When the provider has no transcript or its limit is reached, the report says so; when not configured, the setup message is shown. A test call on 27 November 2026 returned Microsoft's full 2027Q1 call (32 turns, about 48,700 characters, speaker names and titles). Terms (alphavantage.co/terms_of_service): a licence for "personal, non-commercial use", covering "investment analysis, research"; it counts as commercial when used "on behalf of a corporation, firm, partnership, trust or any other association and not as an individual", so ask the professor whether a university group project falls under that; the free key allows 25 requests a day ("unlimited API requests for verified open-source or educational projects").
- **The New analysis button opens an empty form** (decided 27 November 2026): company, peers, transcript and horizon are cleared, live mode and all indicators are selected again; a running analysis carries on under Agent workflow.
- **EDGAR access is allowed.** `data.sec.gov` has no robots.txt; on `www.sec.gov`, `/Archives/edgar/data` is allowed and `/files/` is not blocked (checked 25 November 2026). Requests to sec.gov carry the SEC identification header (`SEC_APP_NAME` + `SEC_CONTACT_EMAIL`).

## Unresolved definitions and assumptions

These choices were open. Most are now resolved by `indicator_definitions.md` v1.0 (marked [x]); the rest remain open and must not be resolved silently in code.

### Items to clarify (from the project brief)

- [x] Definitions of free cash flow (FCF), enterprise value, net debt, NOPAT, and invested capital. Resolved by `indicator_definitions.md` v1.0.
- [x] Treatment of leases, minority interests, preferred shares, and restricted cash. Resolved by `indicator_definitions.md` v1.0.
- [x] Dividend measurement periods. Resolved by `indicator_definitions.md` v1.0.
- [x] Minimum number of historical observations required for a historical comparison. Resolved by `indicator_definitions.md` v1.0.
- [x] Source priority and conflict handling (for example, when two documents disagree). Resolved by `indicator_definitions.md` v1.0.
- [x] Sector-specific exceptions. Resolved by `indicator_definitions.md` v1.0.

### Additional open questions noticed while writing this spec

These are not part of the original brief and are added here for review.

- [x] Share count basis for per-share and market-capitalisation figures (basic or diluted; which date). Resolved by `indicator_definitions.md` v1.0.
- [x] Price date and price currency, and how to handle a reporting currency that differs from the trading currency. Resolved by `indicator_definitions.md` v1.0.
- [x] How TTM figures are constructed from quarterly and cumulative year-to-date reports. Resolved by `indicator_definitions.md` v1.0.
- [ ] What counts as a "completed fiscal year", and how to treat companies with non-calendar fiscal years or changed year-ends.
- [x] How the Graham multiple (P/E × P/B) is labelled so it is never confused with the Graham Number (a share-price formula). Resolved by `indicator_definitions.md` v1.0.
- [x] Which sectors and company types an indicator is "Not applicable" for, and the criteria used to classify a company's sector. Resolved by `indicator_definitions.md` v1.0.

### Decisions on the remaining three-agent points

- **Output language.** English by default; the user can select another. Supported source languages are processed regardless of output language. Original passages are kept beside translated quotations; unsupported languages and uncertain translations are flagged.
- **Uploads.** Documents and audio/video recordings can be uploaded to supplement retrieved material or to provide what the agents cannot access. Uploaded material is labelled separately from independently retrieved official sources.
- **Peer candidates.** Built from an accessible market-data provider's industry classification and company profiles, supplemented by competitors named in official reports and investor presentations. Model-generated suggestions are candidates that need verification by one of those sources. Each candidate's origin is recorded.
- **Selecting peers.** Business model and industry first (products, customer groups, revenue segments, operating model), then geographic exposure (revenue by region where available), then size (revenue and market capitalisation). Missing information is disclosed. Aim for three to five, explain each, never force unsuitable companies in, keep index membership optional, and use transparent criteria rather than presenting a subjective similarity score as an objective fact.
- **User-selected peers.** Counted within the usual three-to-five total; remaining places are filled automatically. Explicit requests for more than five are honoured. A poorly comparable user pick is kept as a clearly labelled user-requested comparison with its limitation explained.
- **Transcription and translation.** The transcription and text-model providers are not chosen yet and stay configurable; provider-specific code is isolated in `backend/llm.py`. (The earlier wording named OpenAI; that was not intended and is withdrawn.) Transcribe in the original language, then translate the text with the configured text model. FFmpeg extracts and splits audio. Timestamps and speaker labels are kept where the model supports them. Long recordings are split with a small overlap, duplicate text at joins is removed, and timestamps stay relative to the original recording. Unclear speech and uncertain speaker identities are flagged; important figures are checked against published documents where possible.
- **Request limits.** One request per second and two concurrent downloads per website host, following any stricter site or provider limit (such as a robots.txt crawl delay). Retry instructions are respected; temporary failures get increasing delays, up to three retries.
- **Saved files.** Retrieved documents are cached and source listings re-checked after 24 hours; changed sources become new versions and old versions are kept. Saved reports keep copies of the exact source versions they cite. Temporary processing files are deleted after seven days. Saved reports and their supporting files are kept until the user deletes them.
- **Recording limits.** 500 MB per file and four hours per recording as initial, configurable operational limits, not permanent scope restrictions. Over the limit, the user is told how to split or compress the file. Long recordings use chunking and background processing with visible progress; failed work resumes without repeating completed steps.
- **Price freshness.** A current valuation uses the latest completed trading session's close on the relevant exchange; earlier data is marked stale, accounting for weekends and market holidays. The price date and currency are always shown. Historical valuations use the requested date and the financial information available then.

### Configurable defaults (`backend/config.py`, overridable in `.env`)

| Setting | Default |
|---|---|
| Output language | English (`DEFAULT_OUTPUT_LANGUAGE=en`) |
| Providers (text model, speech-to-text, market data, news) | None chosen; all settings empty by default (`*_PROVIDER`, `*_API_KEY`, `*_BASE_URL`, `TEXT_MODEL`, `TRANSCRIPTION_MODEL`) |
| Requests per host | 1 per second, 2 concurrent, 3 retries with 1 s, 2 s, 4 s delays |
| Source re-check | 24 hours |
| Temporary files | deleted after 7 days |
| Upload limits | 500 MB per file, 4 hours per recording |
| Recording chunks | 600 s with 5 s overlap |
| Peers | 3 to 5; size counts as similar within 4 times the target's |
| Extra market closures | none (`EXTRA_MARKET_CLOSURES=YYYY-MM-DD,...`) |

### Implementation status

| Feature | Status |
|---|---|
| Output language selection and supported-language checks | Working |
| Document and recording uploads, labelled separately, with size and duration limits | Working |
| Transcription, translation, chunking, de-duplicated joins, flags, figure checks | Working with test doubles; needs a configured provider (not chosen yet) and FFmpeg installed |
| Background jobs with progress and resume | Working |
| Polite fetching (rate, concurrency, robots.txt, Retry-After, retries) | Working |
| Document cache, 24-hour re-check, versions, 7-day temporary cleanup, saved-report copies and deletion | Working |
| Price freshness rules (US exchange holidays, latest completed session, stale flag) | Working |
| Peer selection engine (criteria, origins, verification, user picks, index filter) | Working on supplied candidate data |
| Demo mode, step 1: fictional sample data (5 `.DEMO` companies, reports with page numbers, prices, news, call transcript, recorded Turkish call) and demo stand-ins for market data, news, documents, speech-to-text and translation | Working and tested (22 November 2026); not yet selectable on the website; text-model demo answers come with the agents (step 4) |
| Price retrieval | Awaiting configuration: no market-data provider chosen; requests return a setup message (the Yahoo adapter and default were removed on 18 November 2026) |
| Finding reports on investor relations sites; regulator fallbacks | Awaiting implementation |
| Gathering peer candidates from a provider and from official reports | Awaiting implementation |
| Reading documents with page numbers, step 2: PDF pages, Word sections, Excel sheets, HTML page breaks or sections, text form-feed pages or sections; tables as text rows; scanned PDFs and unreadable files reported with a note (no OCR) | Working and tested (22 November 2026) |
| Finding the relevant pages for a question (keyword ranking, BM25, in Python; each passage keeps its document and page) | Working and tested (22 November 2026) |
| Indicator calculations, step 3: the 20 core indicators above, TTM and fiscal-year history, peer medians; formula, period, status, unit and sources on every result | Working and tested on sample and demo data (22 November 2026) |
| Analysis pipeline, step 4a: company identification, peer choice, Agent 1 (reports read into pages, figures extracted and checked, indicators, checked summary), background progress, `POST /api/analyses`, `GET /api/analyses/{id}`, `GET /api/analyses/{id}/report` | Working and tested in demo mode (22 November 2026); live mode returns the list of services still needed (HTTP 424); not yet on the website |
| Agents 2 and 3, step 4b: earnings call (management, guidance and analysts kept apart), news review with source details, combined report with disagreements, risks, missing information, unverified statements and limitations; wording checks | Working and tested in demo mode (22 November 2026); not yet on the website |
| Website, step 5a: "Run an analysis" box (company, demo tick box, progress, choice when several companies match, list of missing services for a live run) and the report view; `GET /api/analyses/{id}/view` | Working; the layout is tested, the page itself is not yet checked in a browser (22 November 2026) |
| Parts A and B (branch `v3-frontend`): choosing indicators (form, `indicators` in `POST /api/analyses`, catalogue in `/api/config`); the rest of v1.0 section 5 and all of section 6 (59 indicators in 7 groups); standardised CFO/FCF with the reported basis alongside; reported EPS; price returns; historical multiple medians from what was published by each year end; demo reports with the new figures and Q3 reports for 2021–2024 | Working and tested on sample and demo data (25 November 2026) |
| Live analyses from SEC EDGAR: company search and profile, XBRL figures by fiscal period (restatements, filing-date cutoff, composites), SEC identification header, latest 10-K and 10-Q read for the summary, uploaded call transcript, `ask` step for the text model, prices and news shown as not available | Working and tested with fake SEC and OpenAI replies (25 November 2026); not yet run against the real services |
| Twelve Data price adapter: actual and split-adjusted daily closes, one fetch per company per analysis, key in a header, robots.txt exception for `api.twelvedata.com` only, latest completed session for analyses dated today | Working and tested with fake answers (25 November 2026) |
| Automatic peers from EDGAR (same SIC code, ranked by revenue, limited comparability), failure-safe peer search, Twelve Data request spacing | Working and tested (25 November 2026) |
| Horizon of 3, 5 or 10 fiscal years (definitions v1.1), and a New analysis button that opens an empty form | Working and tested (27 November 2026) |
| Earnings-call transcripts from Alpha Vantage: the latest report's fiscal quarter, one request per analysis, speaker turns as citable sections, upload first, notes for missing calls and limits | Working and tested with fake answers; one real test call for Microsoft 2027Q1 (27 November 2026) |
| SEC data gaps: per-period tag choice, Oracle debt tags, cover-page share counts, minority interest per report, estimated dividend yield, percentage-point peer comparisons, reasons for missing values | Working and tested; checked against the real SEC data for MSFT, ORCL, CRM, XYZ, ADBE and INTU without prices (27 November 2026) |
| Parts C (bank module) and D (holding module, with a demo holding company) | Awaiting approval |
| folio. website design (branch `v3-frontend`): six pages, workflow progress per agent, dashboard tabs, SVG chart, sources with details, printable report with cover, mobile menu | Built; tested by page tests and by running the page script against a demo analysis outside a browser; not yet checked in a browser (25 November 2026) |
| PDF (default) and Word download, step 5b: `GET /api/analyses/{id}/download/pdf` and `/docx`, DEMO label on every page | Working and tested (25 November 2026) |

### Still open

- [ ] Richer peer comparison on products, customers and regions (the SEC industry code and revenue size are all the structured data gives).
- [ ] Reports for companies outside SEC EDGAR (investor-relations sites, other regulators), with their own limitations flagged.
- [ ] Bank indicators (v1.0 section 8, part C) and the holding-company module (section 7, part D).
- [ ] Uploaded reports used in place of EDGAR filings.

- [ ] Providers (deliberately left until the end): text model, transcription, market data (prices, profiles, peers, index membership), news, FX rates, and an optional dated consensus source. Yahoo Finance and Stooq disallow automated access in robots.txt.
- [ ] Holiday calendars for non-US exchanges (currently weekends only, flagged as approximate).
- [x] Earnings yield and average daily volume / traded value: kept (see "Decisions after v1.0"). REIT FFO and AFFO: not kept in the core set; add through a sector module or a user request.
- [x] News window and Reuters preference: decided (see "Decisions after v1.0").
- [x] Peer criteria order: confirmed (see "Decisions after v1.0"). How each criterion is measured is set at implementation and must be explained per peer.
- [ ] Optional modules (Piotroski F-score, Altman Z-score, ownership and short interest, forecast measures): deferred; do not expand the scope for them until asked.
- [x] Fiscal years: decided (see "Decisions after v1.0").

### Code changes needed to implement v1.0 (not done yet)

- Done 18 November 2026: provider-neutral settings in `backend/config.py`, `backend/llm.py`, `backend/fetchers/market_data.py`, `.env.example` (placeholders appended; the old `OPENAI_API_KEY` line must be deleted by hand because the deny rule blocks reading the file), `CLAUDE.md`; EDGAR identification setting; setup messages via `backend/services.py`.
- Steps 1–5 of the demo plan are done. The remaining v1.0 indicators come after the core set.
- `backend/peer_selection.py`: add the v1.0 criteria order, the separate group for weak user-selected peers, and peer-median rules.
- `backend/fetchers/`: IR discovery, EDGAR (CIK, 6-K inspection, identification header), amended-filing precedence, wider news relevance.
- `backend/storage.py`: add the provenance fields (consolidation scope, accounting framework, restatement status, definition version, analysis date).
