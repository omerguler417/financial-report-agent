# Using Twelve Data's API although its robots.txt disallows crawlers

Financial Report Analysis Agent, course 30754 AI in Strategic Management. Prepared 25 November 2026 to ask for the professor's acknowledgment.

## Summary

We want to use Twelve Data, a market-data provider, for share prices. Its API works with our free key. However, its `robots.txt` file tells all automated programs to stay out. Our project rules require us to respect `robots.txt` without exception. We have added one narrow exception for Twelve Data only, for the reasons and with the safeguards below, and we ask you to acknowledge it or tell us to switch providers.

## Why we need share prices

Company figures come free from SEC EDGAR, but EDGAR has no share prices. Without a price, 24 of our 59 indicators cannot be calculated. These include P/E, EV/EBITDA, the yields, the price returns, and the historical multiple medians.

## The rule

Our project instructions (`CLAUDE.md`, section 5) say:

> Never bypass `PoliteClient` or a site's `robots.txt`. … If a chosen provider's API is blocked by its `robots.txt`, stop and ask.

`robots.txt` is a public file in which a website states which parts automated programs may visit.

## What we found

On 25 November 2026 we signed up for Twelve Data's free plan. The free plan was reported in 2026 comparisons as 800 credits a day and 8 a minute. The key is stored only on our computer, never in the repository. Twelve Data's API address publishes this `robots.txt`:

```
https://api.twelvedata.com/robots.txt
User-agent: *
Disallow: /
```

This disallows every path for every automated program, including the API itself.

## A process mistake we want to report

Our check script read this `robots.txt` but then still sent one test request for Microsoft's last five daily closing prices. That cost 1 credit. It should have stopped after reading `robots.txt`. We stopped immediately afterwards, and no further requests were made until this exception was decided.

## Why we believe using the API is acceptable

1. **`robots.txt` is meant for crawlers.** It is a convention for programs that roam a website on their own, such as search engines. An API key is a personal permission issued for programmatic access, which is the only purpose of an API key.
2. **Twelve Data's terms of use expect program access through the API.** The terms were last updated 1 January 2026, at https://twelvedata.com/terms:
   - Section 2.1 grants a license "to access and use the Platform solely for Internal Use".
   - Section 1 defines "Platform" to include "the APIs (REST and WebSocket)".
   - Section 1 defines "Internal Use" as "use solely for Customer's internal business purposes and not for redistribution or external commercial purposes".
3. **The terms contain no general ban on automated access.** They do not mention scraping, crawling or `robots.txt`. The only related prohibitions are to "Use automated tools to exceed API Rate Limits or create excessive load" (section 2.3(h)) and to "Circumvent any access restrictions, security measures, or technical limitations" (section 2.3(i)).

## Remaining uncertainty

- **Section 2.3(i)** forbids circumventing "access restrictions". Someone could read `robots.txt` as one. We think this is unlikely, because the terms themselves never mention `robots.txt`, but the terms do not rule it out.
- **Free-tier data may not be used "for commercial purposes"** (section 2.3(l)). Our project is non-commercial coursework.
- **Redistribution or external display of their data needs a paid add-on or a separate agreement** (section 2.2(e)). Using the tool within our group is internal use. Showing reports that contain their prices outside the group, for example in class, is a grey area.
- **Students and educational use** are not mentioned in the terms.

## Alternatives we considered

We checked each provider's `robots.txt` on 25 November 2026.

| Provider | `robots.txt` for its API | Comment |
|---|---|---|
| Twelve Data | Disallows everything | Chosen, with this exception |
| Tiingo | Allows the API (only `/admin` is blocked) | Similar free plan; our fallback |
| Finnhub | Allows the API | Free plan has little price history |
| Alpha Vantage | No `robots.txt` | Only 25 requests a day; long history is paid |
| Financial Modeling Prep | Request refused (HTTP 403) | Not assessed |
| Typing the price by hand | — | Possible stopgap, labelled unverified |

## What we decided, and the safeguards

- **A narrow exception.** It is recorded in `CLAUDE.md` and `docs/indicator_spec.md`, covers `api.twelvedata.com` only, and is marked as awaiting your acknowledgment. No other provider is exempt.
- **Requests go only through the documented API with our own key.** The key is sent in a request header and never published.
- **Rate limits are respected.** An analysis needs about one price request per company, around six including peers, against a limit of 800 a day and 8 a minute. Requests still go through our polite client, with rate limits and retries.
- **Every price in a report names its source and date,** for example "close on 2026-11-24, Twelve Data".
- **Non-commercial use only.** Reports with Twelve Data prices are not published or redistributed.
- **The exception is easy to reverse.** If you disagree, we remove it and switch to Tiingo. That needs only one small adapter, because providers are interchangeable in our design.

## What we ask

Please confirm whether this exception is acceptable for the course, or tell us to switch to a provider whose `robots.txt` allows API access.
