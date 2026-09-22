from pathlib import Path
import os
from types import SimpleNamespace

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from fitbit_report.google_health.oauth import GoogleHealthOAuth, GoogleHealthTokenStore
from fitbit_report.google_health.schemas import GoogleIdentity
from fitbit_report.google_health.schemas import GoogleHealthAuthorizationRequired


def test_google_health_token_store_round_trips_credentials(tmp_path: Path):
    credentials = Credentials(
        token="access",
        refresh_token="refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client",
        client_secret="secret",
        scopes=["scope"],
    )
    store = GoogleHealthTokenStore(tmp_path / "token.json")

    store.save(credentials)
    loaded = store.load()

    assert loaded is not None
    assert loaded.token == "access"
    assert loaded.refresh_token == "refresh"
    if os.name == "posix":
        assert store.path.stat().st_mode & 0o777 == 0o600


def test_identity_parser_keeps_google_and_legacy_ids():
    identity = GoogleIdentity.model_validate(
        {"healthUserId": "google-1", "legacyUserId": "fitbit-1"}
    )

    assert identity.health_user_id == "google-1"
    assert identity.legacy_user_id == "fitbit-1"


def test_refresh_error_is_reported_as_reauthorization_required(tmp_path: Path):
    class RevokedCredentials:
        valid = False
        expired = True
        refresh_token = "revoked"

        def refresh(self, _request):
            raise RefreshError("invalid_grant")

    credentials = RevokedCredentials()
    store = GoogleHealthTokenStore(tmp_path / "token.json")
    oauth = GoogleHealthOAuth(
        SimpleNamespace(google_health_token_path=store.path),
        token_store=store,
    )

    with pytest.raises(GoogleHealthAuthorizationRequired, match="google-health-auth"):
        oauth.refresh_if_needed(credentials)
