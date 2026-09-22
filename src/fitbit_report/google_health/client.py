import time
from collections.abc import Callable, Iterator, Mapping
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from fitbit_report.google_health.oauth import GoogleHealthTokenStore
from fitbit_report.google_health.schemas import (
    GoogleHealthAuthorizationRequired,
    GoogleHealthError,
    GoogleHealthPermissionError,
    GoogleHealthRateLimitError,
    GoogleHealthResponse,
    GoogleHealthTransientError,
    GoogleIdentity,
)


class GoogleHealthClient:
    base_url = "https://health.googleapis.com/v4"

    def __init__(
        self,
        http: httpx.Client,
        credentials: Credentials,
        token_store: GoogleHealthTokenStore | None = None,
        base_url: str | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.http = http
        self.credentials = credentials
        self.token_store = token_store
        self.base_url = (base_url or self.base_url).rstrip("/")
        self.max_retries = max_retries
        self.sleep = sleep

    def get_json(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
    ) -> GoogleHealthResponse:
        return self._request("GET", path, params=params)

    def post_json(self, path: str, body: dict[str, object]) -> GoogleHealthResponse:
        return self._request("POST", path, json_body=body)

    def list_pages(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        query = dict(params or {})
        while True:
            response = self.get_json(path, params=query)
            items = response.payload.get("dataPoints")
            if items is None:
                items = response.payload.get("rollupDataPoints")
            for item in items or []:
                if isinstance(item, dict):
                    yield item
            next_page_token = response.payload.get("nextPageToken")
            if not next_page_token:
                return
            query["page_token"] = str(next_page_token)

    def get_identity(self) -> GoogleIdentity:
        response = self.get_json("users/me/identity")
        return GoogleIdentity.model_validate(response.payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> GoogleHealthResponse:
        url = f"{self.base_url}/{path.lstrip('/')}"
        refreshed_after_401 = False
        retry_count = 0
        while True:
            self._ensure_credentials()
            try:
                response = self.http.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers={
                        "Authorization": f"Bearer {self.credentials.token}",
                        "Accept": "application/json",
                    },
                    timeout=30.0,
                )
            except httpx.TimeoutException as exc:
                if retry_count < self.max_retries:
                    self._wait(retry_count)
                    retry_count += 1
                    continue
                raise GoogleHealthTransientError(f"timeout while requesting {path}") from exc
            except httpx.RequestError as exc:
                if retry_count < self.max_retries:
                    self._wait(retry_count)
                    retry_count += 1
                    continue
                raise GoogleHealthTransientError(f"network error while requesting {path}") from exc

            if response.status_code == 401 and not refreshed_after_401:
                self._refresh_credentials(force=True)
                refreshed_after_401 = True
                continue
            if response.status_code == 403:
                raise GoogleHealthPermissionError(
                    f"Google Health permission denied for {path} (status=403)"
                )
            if response.status_code == 429:
                if retry_count < self.max_retries:
                    self._wait(retry_count)
                    retry_count += 1
                    continue
                raise GoogleHealthRateLimitError(
                    f"Google Health rate limit reached for {path} (status=429)"
                )
            if response.status_code >= 500:
                if retry_count < self.max_retries:
                    self._wait(retry_count)
                    retry_count += 1
                    continue
                raise GoogleHealthTransientError(
                    f"Google Health server error for {path} (status={response.status_code})"
                )
            if response.status_code >= 400:
                raise GoogleHealthError(
                    f"Google Health request failed for {path} (status={response.status_code})"
                )

            payload = response.json()
            if not isinstance(payload, dict):
                raise GoogleHealthError(f"Google Health returned a non-object payload for {path}")
            return GoogleHealthResponse(status_code=response.status_code, payload=payload)

    def _ensure_credentials(self) -> None:
        if self.credentials.valid:
            return
        self._refresh_credentials()

    def _refresh_credentials(self, *, force: bool = False) -> None:
        if (not force and not self.credentials.expired) or not self.credentials.refresh_token:
            raise GoogleHealthAuthorizationRequired(
                "Google Health authorization is missing or cannot be refreshed"
            )
        try:
            self.credentials.refresh(Request())
        except RefreshError as exc:
            raise GoogleHealthAuthorizationRequired(
                "Google Health authorization expired or was revoked. Run google-health-auth again."
            ) from exc
        if self.token_store is not None:
            self.token_store.save(self.credentials)

    def _wait(self, retry_count: int) -> None:
        self.sleep(min(2**retry_count, 8))
