from pathlib import Path

import httpx
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from fitbit_report.config import Settings
from fitbit_report.google_health.schemas import (
    GoogleHealthAuthorizationRequired,
    GoogleIdentity,
)
from fitbit_report.private_storage import write_private_text


class GoogleHealthTokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Credentials | None:
        if not self.path.exists():
            return None
        return Credentials.from_authorized_user_file(str(self.path))

    def save(self, credentials: Credentials) -> None:
        write_private_text(self.path, credentials.to_json())


class GoogleHealthOAuth:
    def __init__(
        self,
        settings: Settings,
        token_store: GoogleHealthTokenStore | None = None,
        http: httpx.Client | None = None,
    ):
        self.settings = settings
        self.token_store = token_store or GoogleHealthTokenStore(
            settings.google_health_token_path
        )
        self.http = http or httpx.Client(timeout=30.0)

    def authorize(self) -> Credentials:
        if not self.settings.google_health_client_secrets.exists():
            raise GoogleHealthAuthorizationRequired(
                "Google OAuth client secrets file is missing: "
                f"{self.settings.google_health_client_secrets}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.settings.google_health_client_secrets),
            scopes=self.settings.google_health_scope_urls(),
        )
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=8765,
            open_browser=True,
            access_type="offline",
            prompt="consent",
        )
        self.token_store.save(credentials)
        return credentials

    def refresh_if_needed(self, credentials: Credentials) -> Credentials:
        if credentials.valid:
            return credentials
        if not credentials.expired or not credentials.refresh_token:
            raise GoogleHealthAuthorizationRequired(
                "Google Health authorization is missing or cannot be refreshed"
            )
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            raise GoogleHealthAuthorizationRequired(
                "Google Health authorization expired or was revoked. Run google-health-auth again."
            ) from exc
        self.token_store.save(credentials)
        return credentials

    def get_identity(self, credentials: Credentials | None = None) -> GoogleIdentity:
        current = credentials or self.token_store.load()
        if current is None:
            raise GoogleHealthAuthorizationRequired(
                "Run google-health-auth before requesting Google Health data"
            )
        current = self.refresh_if_needed(current)
        response = self.http.get(
            "https://health.googleapis.com/v4/users/me/identity",
            headers={
                "Authorization": f"Bearer {current.token}",
                "Accept": "application/json",
            },
        )
        if response.status_code == 401:
            current = self.refresh_if_needed(current)
            response = self.http.get(
                "https://health.googleapis.com/v4/users/me/identity",
                headers={
                    "Authorization": f"Bearer {current.token}",
                    "Accept": "application/json",
                },
            )
        response.raise_for_status()
        return GoogleIdentity.model_validate(response.json())
