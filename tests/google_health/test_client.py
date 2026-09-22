from collections.abc import Callable

import httpx
import pytest

from fitbit_report.google_health.client import GoogleHealthClient
from fitbit_report.google_health.schemas import (
    GoogleHealthPermissionError,
    GoogleHealthRateLimitError,
)


class FakeCredentials:
    def __init__(self):
        self.token = "old"
        self.refresh_token = "refresh"
        self.expired = False
        self.refresh_count = 0

    @property
    def valid(self):
        return bool(self.token)

    def refresh(self, request):
        del request
        self.refresh_count += 1
        self.token = "new"


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> GoogleHealthClient:
    return GoogleHealthClient(
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        credentials=FakeCredentials(),
        max_retries=0,
    )


def test_client_retries_once_after_401_and_refreshes_credentials():
    calls = []

    def handler(request):
        calls.append(request.headers["authorization"])
        if len(calls) == 1:
            return httpx.Response(401, json={"error": "invalid_token"})
        return httpx.Response(200, json={"dataPoints": []})

    client = make_client(handler)

    assert client.get_json("users/me/profile").status_code == 200
    assert calls == ["Bearer old", "Bearer new"]


def test_list_pages_follows_next_page_token():
    def handler(request):
        if request.url.params.get("page_token") == "second":
            return httpx.Response(200, json={"dataPoints": [{"value": 2}]})
        return httpx.Response(
            200,
            json={"dataPoints": [{"value": 1}], "nextPageToken": "second"},
        )

    client = make_client(handler)

    assert list(client.list_pages("users/me/dataTypes/steps/dataPoints")) == [
        {"value": 1},
        {"value": 2},
    ]


def test_client_raises_typed_errors_for_403_and_429():
    def forbidden(request):
        return httpx.Response(403, json={"error": "permission_denied"})

    def limited(request):
        return httpx.Response(429, json={"error": "rate_limited"})

    with pytest.raises(GoogleHealthPermissionError):
        make_client(forbidden).get_json("users/me/profile")
    with pytest.raises(GoogleHealthRateLimitError):
        make_client(limited).get_json("users/me/profile")
