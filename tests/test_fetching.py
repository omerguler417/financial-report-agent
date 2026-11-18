# Polite fetching (rate and concurrency limits, robots.txt, Retry-After, backoff) and the document cache (24-hour re-check, versions).
from datetime import datetime, timedelta, timezone

import httpx2
import pytest

from backend.fetchers.filings import retrieve_document
from backend.fetchers.http_client import AccessDenied, FetchFailed, PoliteClient
from backend.storage import ORIGIN_OFFICIAL, Store
from tests.helpers import FakeClock, make_settings


def client_for(tmp_path, handler, **overrides):
    fc = FakeClock()
    settings = make_settings(tmp_path, **overrides)
    return PoliteClient(settings, transport=httpx2.MockTransport(handler), sleep=fc.sleep, clock=fc.clock), fc, settings


def no_robots(responses):
    """Handler: robots.txt missing, then serve the given responses in order."""
    queue = list(responses)

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx2.Response(404)
        return queue.pop(0) if len(queue) > 1 else queue[0]
    return handler


def test_one_request_per_second_per_host(tmp_path):
    client, fc, _ = client_for(tmp_path, no_robots([httpx2.Response(200, text="ok")]))
    client.get("https://ir.example.com/a")
    client.get("https://ir.example.com/b")
    assert fc.sleeps == [1.0, 1.0]  # robots.txt, then a, then b: each spaced by 1 second


def test_hosts_are_limited_separately_and_concurrency_is_two(tmp_path):
    client, fc, _ = client_for(tmp_path, no_robots([httpx2.Response(200)]))
    client.get("https://one.example.com/a")
    client.get("https://two.example.com/a")
    assert fc.sleeps == [1.0, 1.0]  # one wait per host after its robots.txt, none across hosts
    assert client._host("one.example.com").slots._value == 2


def test_stricter_crawl_delay_wins(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx2.Response(200, text="User-agent: *\nCrawl-delay: 5\nAllow: /\n")
        return httpx2.Response(200)
    client, fc, _ = client_for(tmp_path, handler)
    client.get("https://slow.example.com/a")
    client.get("https://slow.example.com/b")
    assert fc.sleeps[-1] == 5.0


def test_retry_after_is_respected(tmp_path):
    client, fc, _ = client_for(tmp_path, no_robots([httpx2.Response(503, headers={"Retry-After": "7"}), httpx2.Response(200)]),
                               min_seconds_between_requests_per_host=0.0)
    assert client.get("https://x.example.com/a").status_code == 200
    assert 7.0 in fc.sleeps


def test_increasing_delays_then_give_up_after_three_retries(tmp_path):
    client, fc, _ = client_for(tmp_path, no_robots([httpx2.Response(500)]), min_seconds_between_requests_per_host=0.0)
    with pytest.raises(FetchFailed, match="after 3 retries"):
        client.get("https://x.example.com/a")
    assert [s for s in fc.sleeps if s] == [1.0, 2.0, 4.0]


def test_robots_disallow_and_403_are_never_bypassed(tmp_path):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx2.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx2.Response(403)
    client, _, _ = client_for(tmp_path, handler)
    with pytest.raises(AccessDenied, match="robots.txt"):
        client.get("https://x.example.com/private/report.pdf")
    with pytest.raises(AccessDenied, match="403"):
        client.get("https://x.example.com/public/report.pdf")


def test_document_cache_rechecks_after_24_hours_and_keeps_versions(tmp_path):
    bodies = [b"version one", b"version one", b"version two"]
    calls = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx2.Response(404)
        calls.append(req.url.path)
        return httpx2.Response(200, content=bodies[len(calls) - 1], headers={"content-type": "application/pdf"})

    client, _, settings = client_for(tmp_path, handler)
    store = Store(settings.storage_dir)
    url = "https://ir.example.com/q3-2026.pdf"
    t0 = datetime(2026, 11, 1, tzinfo=timezone.utc)

    meta, status = retrieve_document(url, store, client, settings, reporting_period="Q3 2026", publication_date="2026-10-30", now=t0)
    assert status == "new" and meta["origin"] == ORIGIN_OFFICIAL and meta["source_url"] == url
    assert meta["reporting_period"] == "Q3 2026" and meta["publication_date"] == "2026-10-30"
    assert meta["versions"][0]["retrieved_at"].startswith("2026-11-01")

    _, status = retrieve_document(url, store, client, settings, now=t0 + timedelta(hours=23))
    assert status == "cached" and len(calls) == 1

    _, status = retrieve_document(url, store, client, settings, now=t0 + timedelta(hours=25))
    assert status == "unchanged" and len(calls) == 2

    meta, status = retrieve_document(url, store, client, settings, now=t0 + timedelta(hours=50))
    assert status == "updated" and [v["version"] for v in meta["versions"]] == [1, 2]
    assert store.version_path(meta, 1).read_bytes() == b"version one"
