"""Socrata SODA 2.1 client: keyset pagination, retries with backoff.

Why keyset pagination (``$order=:id`` + ``:id > last``) instead of
``$offset``: these are live datasets that receive inserts while we page
through them. Offset pagination shifts under you, producing duplicated or
skipped rows; keyset pagination over the immutable row id is stable and is
Socrata's documented approach for paging large datasets.
"""

import logging
import random
import time
from collections.abc import Iterator

import requests

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Request system fields alongside the payload: ``:id`` drives keyset
# pagination; ``:updated_at`` drives incremental watermarks uniformly across
# sources (it also captures in-place updates, e.g. a 311 status change).
# Note SoQL requires ``:*`` / ``*`` star selections at the start of the list.
SYSTEM_SELECT = ":*,*"


class SocrataError(RuntimeError):
    """Non-retryable API failure, or retries exhausted."""


class SocrataClient:
    def __init__(
        self,
        domain: str,
        app_token: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        backoff_cap: float = 60.0,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ) -> None:
        self._domain = domain
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._sleep = sleep
        self._session = session or requests.Session()
        if app_token:
            self._session.headers["X-App-Token"] = app_token

    def _url(self, dataset_id: str) -> str:
        return f"https://{self._domain}/resource/{dataset_id}.json"

    def _get(self, url: str, params: dict) -> list[dict]:
        """GET with exponential backoff + jitter on 429/5xx/connection errors."""
        last_error: str = "unknown"
        for attempt in range(self._max_retries + 1):
            retry_after: str | None = None
            try:
                response = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                last_error = f"connection error: {exc}"
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRYABLE_STATUS:
                    raise SocrataError(
                        f"HTTP {response.status_code} from {url}: {response.text[:500]}"
                    )
                last_error = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After")

            if attempt >= self._max_retries:
                break
            delay = min(self._backoff_cap, self._backoff_base * (2**attempt))
            if retry_after is not None:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
            delay += random.uniform(0, delay * 0.25)
            logger.warning(
                "socrata_retry",
                extra={"url": url, "attempt": attempt + 1, "reason": last_error, "sleep_s": round(delay, 1)},
            )
            self._sleep(delay)
        raise SocrataError(f"retries exhausted for {url}: {last_error}")

    def iter_pages(
        self,
        dataset_id: str,
        where: str | None = None,
        page_size: int = 10_000,
        max_records: int | None = None,
        select_fields: tuple[str, ...] | None = None,
    ) -> Iterator[list[dict]]:
        """Yield pages of records using keyset pagination on ``:id``.

        ``where`` is a SoQL filter applied to every page (e.g. a dev sample
        window or an incremental ``:updated_at`` predicate). ``select_fields``
        projects specific payload columns (system fields are always added).
        """
        select = SYSTEM_SELECT if not select_fields else ":id,:updated_at," + ",".join(select_fields)
        url = self._url(dataset_id)
        last_id: str | None = None
        fetched = 0
        while True:
            remaining = max_records - fetched if max_records is not None else page_size
            limit = min(page_size, remaining)
            if limit <= 0:
                return
            clauses = []
            if where:
                clauses.append(f"({where})")
            if last_id is not None:
                clauses.append(f"(:id > '{last_id}')")
            params: dict = {"$select": select, "$order": ":id", "$limit": limit}
            if clauses:
                params["$where"] = " AND ".join(clauses)
            rows = self._get(url, params)
            if not rows:
                return
            fetched += len(rows)
            last_id = rows[-1][":id"]
            yield rows
            if len(rows) < limit:
                return
