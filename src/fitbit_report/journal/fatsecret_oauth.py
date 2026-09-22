"""OAuth 1.0 client for reading a linked FatSecret member food diary."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode

import httpx


REQUEST_TOKEN_URL = "https://authentication.fatsecret.com/oauth/request_token"
AUTHORIZE_URL = "https://authentication.fatsecret.com/oauth/authorize"
ACCESS_TOKEN_URL = "https://authentication.fatsecret.com/oauth/access_token"
FOOD_ENTRIES_URL = "https://platform.fatsecret.com/rest/food-entries/v2"


class FatSecretOAuthError(RuntimeError):
    """A user-safe error raised by FatSecret OAuth or diary requests."""


@dataclass(frozen=True)
class FatSecretAuthorizationStart:
    request_token: str
    request_token_secret: str
    authorization_url: str


@dataclass(frozen=True)
class FatSecretAccessToken:
    token: str
    secret: str


@dataclass(frozen=True)
class FatSecretDiaryEntry:
    meal_type: str
    food_name: str
    serving: str | None
    calories: float | None
    fat_g: float | None
    saturated_fat_g: float | None
    carbohydrates_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    protein_g: float | None
    sodium_mg: float | None
    cholesterol_mg: float | None
    potassium_mg: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "meal_type": self.meal_type,
            "food_name": self.food_name,
            "serving": self.serving,
            "calories": self.calories,
            "fat_g": self.fat_g,
            "saturated_fat_g": self.saturated_fat_g,
            "carbohydrates_g": self.carbohydrates_g,
            "fiber_g": self.fiber_g,
            "sugar_g": self.sugar_g,
            "protein_g": self.protein_g,
            "sodium_mg": self.sodium_mg,
            "cholesterol_mg": self.cholesterol_mg,
            "potassium_mg": self.potassium_mg,
        }


def _quote(value: object) -> str:
    return quote(str(value), safe="~")


def _oauth_signature(
    method: str,
    url: str,
    parameters: dict[str, str],
    consumer_secret: str,
    token_secret: str | None,
) -> str:
    normalized_parameters = "&".join(
        f"{_quote(key)}={_quote(value)}"
        for key, value in sorted(parameters.items())
    )
    base = "&".join(
        (_quote(method.upper()), _quote(url), _quote(normalized_parameters))
    )
    key = f"{_quote(consumer_secret)}&{_quote(token_secret or '')}"
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _as_entries(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    container = payload.get("food_entries")
    if not isinstance(container, dict):
        return []
    rows = container.get("food_entry", [])
    if isinstance(rows, dict):
        return [rows]
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


class FatSecretOAuthClient:
    def __init__(self, consumer_key: str, consumer_secret: str, http: httpx.Client | None = None):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.http = http or httpx.Client(timeout=30, follow_redirects=True)
        self._owns_http = http is None

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def __enter__(self) -> "FatSecretOAuthClient":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
        oauth_parameters: dict[str, str] | None = None,
        token: str | None = None,
        token_secret: str | None = None,
        oauth_in_query: bool = False,
    ) -> httpx.Response:
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_version": "1.0",
        }
        # Flow fields are OAuth protocol parameters, not FatSecret API filters.
        # Keeping them in the signed Authorization header matches the provider's
        # three-legged OAuth specification.
        oauth_params.update(oauth_parameters or {})
        if token:
            oauth_params["oauth_token"] = token
        signature_params = {**(params or {}), **oauth_params}
        oauth_params["oauth_signature"] = _oauth_signature(
            method,
            url,
            signature_params,
            self.consumer_secret,
            token_secret,
        )
        request_params = dict(params or {})
        headers: dict[str, str] = {}
        if oauth_in_query:
            # The currently deployed FatSecret OAuth endpoints accept the
            # three-legged handshake as signed GET query parameters.
            request_params.update(oauth_params)
        else:
            authorization = "OAuth " + ", ".join(
                f'{_quote(key)}="{_quote(value)}"'
                for key, value in sorted(oauth_params.items())
            )
            headers["Authorization"] = authorization
        try:
            response = self.http.request(
                method,
                url,
                params=request_params or None,
                headers=headers,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                detail = (
                    "FatSecret отклонил OAuth-ключи (HTTP "
                    f"{status}). Проверь, что в .env указаны именно Client ID и "
                    "Consumer Secret из REST API OAuth 1.0 Credentials, без кавычек и пробелов."
                )
            else:
                detail = f"FatSecret ответил ошибкой HTTP {status}. Попробуй ещё раз позже."
            raise FatSecretOAuthError(detail) from exc
        except httpx.HTTPError as exc:
            raise FatSecretOAuthError(
                "Не удалось связаться с FatSecret. Проверь подключение сервера и попробуй ещё раз."
            ) from exc

    def start_authorization(self) -> FatSecretAuthorizationStart:
        response = self._request(
            "GET",
            REQUEST_TOKEN_URL,
            oauth_parameters={"oauth_callback": "oob"},
            oauth_in_query=True,
        )
        values = dict(parse_qsl(response.text, keep_blank_values=True))
        token = values.get("oauth_token")
        secret = values.get("oauth_token_secret")
        if not token or not secret:
            raise FatSecretOAuthError("FatSecret не вернул код для привязки аккаунта.")
        return FatSecretAuthorizationStart(
            request_token=token,
            request_token_secret=secret,
            authorization_url=f"{AUTHORIZE_URL}?{urlencode({'oauth_token': token})}",
        )

    def complete_authorization(
        self, request_token: str, request_token_secret: str, verifier: str
    ) -> FatSecretAccessToken:
        response = self._request(
            "GET",
            ACCESS_TOKEN_URL,
            oauth_parameters={"oauth_verifier": verifier},
            token=request_token,
            token_secret=request_token_secret,
            oauth_in_query=True,
        )
        values = dict(parse_qsl(response.text, keep_blank_values=True))
        token = values.get("oauth_token")
        secret = values.get("oauth_token_secret")
        if not token or not secret:
            raise FatSecretOAuthError("Код FatSecret не подошёл. Запусти привязку заново.")
        return FatSecretAccessToken(token=token, secret=secret)

    def fetch_food_diary(
        self, day: date, access_token: str, access_token_secret: str
    ) -> tuple[list[FatSecretDiaryEntry], dict[str, object]]:
        epoch_day = (day - date(1970, 1, 1)).days
        response = self._request(
            "GET",
            FOOD_ENTRIES_URL,
            params={"date": str(epoch_day), "format": "json"},
            token=access_token,
            token_secret=access_token_secret,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FatSecretOAuthError("FatSecret вернул ответ в неожиданном формате.") from exc
        entries = []
        for row in _as_entries(payload):
            meal = str(row.get("meal") or "other").casefold()
            entries.append(
                FatSecretDiaryEntry(
                    meal_type=meal if meal in {"breakfast", "lunch", "dinner", "other", "snack"} else "other",
                    food_name=str(row.get("food_entry_name") or row.get("food_entry_description") or "Продукт"),
                    serving=str(row.get("food_entry_description") or "").strip() or None,
                    calories=_as_float(row.get("calories")),
                    fat_g=_as_float(row.get("fat")),
                    saturated_fat_g=_as_float(row.get("saturated_fat")),
                    carbohydrates_g=_as_float(row.get("carbohydrate")),
                    fiber_g=_as_float(row.get("fiber")),
                    sugar_g=_as_float(row.get("sugar")),
                    protein_g=_as_float(row.get("protein")),
                    sodium_mg=_as_float(row.get("sodium")),
                    cholesterol_mg=_as_float(row.get("cholesterol")),
                    potassium_mg=_as_float(row.get("potassium")),
                )
            )
        return entries, payload if isinstance(payload, dict) else {}
