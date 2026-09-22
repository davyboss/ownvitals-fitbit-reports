from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class GoogleIdentity(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    health_user_id: str = Field(
        validation_alias=AliasChoices("healthUserId", "health_user_id")
    )
    legacy_user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("legacyUserId", "legacy_user_id"),
    )


class GoogleHealthResponse(BaseModel):
    status_code: int
    payload: dict[str, Any]


class GoogleHealthError(RuntimeError):
    """Base error for Google Health API integration failures."""


class GoogleHealthAuthorizationRequired(GoogleHealthError):
    """The user must authorize or re-authorize the application."""


class GoogleHealthPermissionError(GoogleHealthError):
    """The authorized account lacks a requested Google Health permission."""


class GoogleHealthRateLimitError(GoogleHealthError):
    """Google Health API rate limit was reached."""


class GoogleHealthTransientError(GoogleHealthError):
    """A retryable network or server failure occurred."""
