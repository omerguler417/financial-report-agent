# Polite HTTP client shared by all fetchers: per-host rate and concurrency limits, robots.txt, Retry-After, and increasing retry delays.
import threading
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx2

from backend.config import Settings

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 300


# Hosts whose robots.txt is not applied, each decided by the group and recorded in CLAUDE.md. No other host is exempt.
ROBOTS_EXCEPTIONS = {
    "api.twelvedata.com": "Twelve Data's official API used with the group's own key (CLAUDE.md; docs/twelvedata_robots_exception.md)",
}


class AccessDenied(Exception):
    """The site's rules or response forbid this request. We never try to get around it."""


class FetchFailed(Exception):
    pass


class _Host:
    def __init__(self, max_concurrent: int):
        self.slots = threading.Semaphore(max_concurrent)
        self.lock = threading.Lock()
        self.last_request = None
        self.robots = None
        self.robots_loaded = False
        self.crawl_delay = 0.0
        self.min_interval = 0.0  # a provider's own pace, for example a per-minute request limit


class PoliteClient:
    def __init__(self, settings: Settings, transport=None, sleep=time.sleep, clock=time.monotonic):
        self.settings = settings
        self.sleep = sleep
        self.clock = clock
        self._hosts: dict[str, _Host] = {}
        self._hosts_lock = threading.Lock()
        self._client = httpx2.Client(
            transport=transport,
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        )

    def close(self):
        self._client.close()

    def _host(self, host: str) -> _Host:
        with self._hosts_lock:
            if host not in self._hosts:
                self._hosts[host] = _Host(self.settings.max_concurrent_downloads_per_host)
            return self._hosts[host]

    def _wait_for_turn(self, state: _Host) -> None:
        interval = max(self.settings.min_seconds_between_requests_per_host, state.crawl_delay, state.min_interval)
        with state.lock:
            if state.last_request is not None:
                remaining = interval - (self.clock() - state.last_request)
                if remaining > 0:
                    self.sleep(remaining)
            state.last_request = self.clock()

    def set_min_interval(self, host: str, seconds: float) -> None:
        """Space requests to one host at least `seconds` apart, for a provider's per-minute limit."""
        self._host(host.lower()).min_interval = seconds

    def _backoff(self, attempt: int) -> float:
        return self.settings.backoff_base_seconds * (2 ** attempt)

    @staticmethod
    def retry_after_seconds(response) -> float | None:
        value = response.headers.get("retry-after")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                return None

    def _load_robots(self, scheme: str, host: str, state: _Host) -> None:
        if state.robots_loaded:
            return
        state.robots_loaded = True
        parser = RobotFileParser()
        try:
            response = self._send(f"{scheme}://{host}/robots.txt", state)
        except FetchFailed:
            return  # robots.txt unreachable: no rules to apply
        if response.status_code in (401, 403):
            parser.disallow_all = True
        elif response.status_code >= 400:
            parser.allow_all = True
        else:
            parser.parse(response.text.splitlines())
            delay = parser.crawl_delay(self.settings.user_agent)
            if delay:
                state.crawl_delay = float(delay)  # stricter site rule wins
        state.robots = parser

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.netloc.lower() in ROBOTS_EXCEPTIONS:
            return True
        state = self._host(parts.netloc)
        self._load_robots(parts.scheme, parts.netloc, state)
        return state.robots is None or state.robots.can_fetch(self.settings.user_agent, url)

    def _headers_for(self, url: str) -> dict | None:
        """The SEC asks automated clients to identify themselves with an application name and a contact address."""
        host = urlsplit(url).netloc.lower()
        if (host == "sec.gov" or host.endswith(".sec.gov")) and self.settings.sec_user_agent:
            return {"User-Agent": self.settings.sec_user_agent}
        return None

    def _send(self, url: str, state: _Host, headers: dict | None = None):
        """One request with rate limits and retries; returns the final response."""
        attempts = self.settings.max_retries + 1
        for attempt in range(attempts):
            with state.slots:
                self._wait_for_turn(state)
                try:
                    response = self._client.get(url, headers={**(self._headers_for(url) or {}), **(headers or {})} or None)
                except httpx2.TransportError as exc:
                    if attempt == attempts - 1:
                        raise FetchFailed(f"{url}: {exc}") from exc
                    self.sleep(self._backoff(attempt))
                    continue
            if response.status_code not in RETRYABLE_STATUS:
                return response
            wait = self.retry_after_seconds(response)
            if wait is not None and wait > MAX_RETRY_AFTER_SECONDS:
                raise FetchFailed(f"{url}: the server asked us to wait {wait:.0f}s before retrying; try again later.")
            if attempt == attempts - 1:
                raise FetchFailed(f"{url}: HTTP {response.status_code} after {self.settings.max_retries} retries.")
            self.sleep(wait if wait is not None else self._backoff(attempt))
        raise FetchFailed(url)  # unreachable

    def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        if params:
            url = str(httpx2.URL(url, params=params))
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise FetchFailed(f"Unsupported URL: {url}")
        if not self.allowed(url):
            raise AccessDenied(f"{url} is disallowed by {parts.netloc}/robots.txt")
        response = self._send(url, self._host(parts.netloc), headers)
        if response.status_code in (401, 403):
            raise AccessDenied(f"{url}: access refused (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise FetchFailed(f"{url}: HTTP {response.status_code}.")
        return response
