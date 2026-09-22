from __future__ import annotations

import json
from pathlib import Path

import httpx


class RichMessageError(RuntimeError):
    """Raised when Telegram cannot accept the rich report."""


async def send_rich_report(
    *,
    token: str,
    chat_id: int,
    rich_html: str,
    chart_path: Path | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    rich_message: dict[str, object] = {
        "html": rich_html,
        "skip_entity_detection": True,
    }
    if chart_path is not None:
        rich_message["media"] = [
            {
                "id": "report_chart",
                "media": {"type": "photo", "media": "attach://report_chart"},
            }
        ]

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=90)
    try:
        try:
            if chart_path is None:
                response = await http.post(
                    f"https://api.telegram.org/bot{token}/sendRichMessage",
                    json={"chat_id": chat_id, "rich_message": rich_message},
                )
            else:
                with chart_path.open("rb") as chart:
                    response = await http.post(
                        f"https://api.telegram.org/bot{token}/sendRichMessage",
                        data={
                            "chat_id": str(chat_id),
                            "rich_message": json.dumps(rich_message),
                        },
                        files={
                            "report_chart": (chart_path.name, chart, "image/png"),
                        },
                    )
        except (httpx.HTTPError, OSError):
            raise RichMessageError("Telegram rich report request failed") from None
        try:
            payload = response.json()
        except ValueError:
            raise RichMessageError(
                f"Telegram rich report returned status {response.status_code}"
            ) from None
        if not payload.get("ok"):
            description = payload.get("description", "request rejected")
            raise RichMessageError(f"Telegram rejected rich report: {description}")
    finally:
        if owns_client:
            await http.aclose()
