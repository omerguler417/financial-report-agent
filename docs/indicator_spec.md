# Indicator Specification (future requirements)

Status: requirements plus implementation status. See "Implementation status" at the end for what already works.

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

- Consider only items published after the date of the latest quarterly report.
- Sources: company announcements for official disclosures; Reuters as the preferred independent news source when accessible; other established financial news outlets as fallbacks. For every item include the publisher, publication date and link.
- Distinguish management statements from independent reporting.
- Unusual or relevant events are controversies, political or cultural events that may affect the company specifically or its relevant index, and new regulations. Also include other recent news about the company in that period.
- Make no claim about whether news is already reflected in the share price. Do not claim that news caused a share-price movement solely because their timing overlaps.

### Market data

- Use one consistent market-data provider through a supported, permitted access method. Yahoo Finance is acceptable for the prototype where access permits.
- For every price record the ticker, exchange, currency, source and price timestamp, and flag stale data.
- Use the relevant closing price for dated valuations and adjusted prices for historical return comparisons.
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

### Decisions on the remaining three-agent points

- **Output language.** English by default; the user can select another. Supported source languages are processed regardless of output language. Original passages are kept beside translated quotations; unsupported languages and uncertain translations are flagged.
- **Uploads.** Documents and audio/video recordings can be uploaded to supplement retrieved material or to provide what the agents cannot access. Uploaded material is labelled separately from independently retrieved official sources.
- **Peer candidates.** Built from an accessible market-data provider's industry classification and company profiles, supplemented by competitors named in official reports and investor presentations. Model-generated suggestions are candidates that need verification by one of those sources. Each candidate's origin is recorded.
- **Selecting peers.** Business model and industry first (products, customer groups, revenue segments, operating model), then geographic exposure (revenue by region where available), then size (revenue and market capitalisation). Missing information is disclosed. Aim for three to five, explain each, never force unsuitable companies in, keep index membership optional, and use transparent criteria rather than presenting a subjective similarity score as an objective fact.
- **User-selected peers.** Counted within the usual three-to-five total; remaining places are filled automatically. Explicit requests for more than five are honoured. A poorly comparable user pick is kept as a clearly labelled user-requested comparison with its limitation explained.
- **Transcription and translation.** OpenAI's transcription API first, with the transcription and text models configurable and provider-specific code isolated in `backend/llm.py`. Transcribe in the original language, then translate the text with the configured text model. FFmpeg extracts and splits audio. Timestamps and speaker labels are kept where the model supports them. Long recordings are split with a small overlap, duplicate text at joins is removed, and timestamps stay relative to the original recording. Unclear speech and uncertain speaker identities are flagged; important figures are checked against published documents where possible.
- **Request limits.** One request per second and two concurrent downloads per website host, following any stricter site or provider limit (such as a robots.txt crawl delay). Retry instructions are respected; temporary failures get increasing delays, up to three retries.
- **Saved files.** Retrieved documents are cached and source listings re-checked after 24 hours; changed sources become new versions and old versions are kept. Saved reports keep copies of the exact source versions they cite. Temporary processing files are deleted after seven days. Saved reports and their supporting files are kept until the user deletes them.
- **Recording limits.** 500 MB per file and four hours per recording as initial, configurable operational limits, not permanent scope restrictions. Over the limit, the user is told how to split or compress the file. Long recordings use chunking and background processing with visible progress; failed work resumes without repeating completed steps.
- **Price freshness.** A current valuation uses the latest completed trading session's close on the relevant exchange; earlier data is marked stale, accounting for weekends and market holidays. The price date and currency are always shown. Historical valuations use the requested date and the financial information available then.

### Configurable defaults (`backend/config.py`, overridable in `.env`)

| Setting | Default |
|---|---|
| Output language | English (`DEFAULT_OUTPUT_LANGUAGE=en`) |
| Transcription model / text model | `whisper-1` / `gpt-4.1-mini` (`TRANSCRIPTION_MODEL`, `TEXT_MODEL`) |
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
| Transcription, translation, chunking, de-duplicated joins, flags, figure checks | Working; needs `OPENAI_API_KEY` in `.env` and FFmpeg installed |
| Background jobs with progress and resume | Working |
| Polite fetching (rate, concurrency, robots.txt, Retry-After, retries) | Working |
| Document cache, 24-hour re-check, versions, 7-day temporary cleanup, saved-report copies and deletion | Working |
| Price freshness rules (US exchange holidays, latest completed session, stale flag) | Working |
| Peer selection engine (criteria, origins, verification, user picks, index filter) | Working on supplied candidate data |
| Price retrieval from Yahoo Finance | Blocked: Yahoo's robots.txt disallows automated access, so the client refuses it |
| Finding reports on investor relations sites; regulator fallbacks | Awaiting implementation |
| Gathering peer candidates from a provider and from official reports | Awaiting implementation |
| PDF, Word and Excel text extraction | Awaiting implementation (plain text and HTML work) |
| Agents 1, 2 and 3, indicator calculations, final PDF/Word report | Awaiting implementation |

### Still open

- [ ] A price and company-profile provider with a permitted, supported access method (an official API with a key, for example). Yahoo Finance and Stooq both disallow automated access in robots.txt.
- [ ] Confirm the default text model for translation; the default is a placeholder that can be changed in `.env`.
- [ ] Holiday calendars for non-US exchanges (currently weekends only, flagged as approximate).
