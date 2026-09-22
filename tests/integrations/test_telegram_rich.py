import asyncio
import json
from pathlib import Path

import httpx

from fitbit_report.integrations.telegram_rich import send_rich_report


def test_send_rich_report_posts_json_without_chart():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await send_rich_report(
                token="secret",
                chat_id=42,
                rich_html="<h1>Report</h1>",
                client=client,
            )

    asyncio.run(run())

    payload = json.loads(requests[0].content)
    assert requests[0].url.path.endswith("/sendRichMessage")
    assert payload == {
        "chat_id": 42,
        "rich_message": {
            "html": "<h1>Report</h1>",
            "skip_entity_detection": True,
        },
    }


def test_send_rich_report_attaches_chart(tmp_path: Path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    chart = tmp_path / "chart.png"
    chart.write_bytes(b"valid-test-png")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await send_rich_report(
                token="secret",
                chat_id=42,
                rich_html='<figure><img src="tg://photo?id=report_chart"/></figure>',
                chart_path=chart,
                client=client,
            )

    asyncio.run(run())

    request = requests[0]
    assert "multipart/form-data" in request.headers["content-type"]
    assert b'attach://report_chart' in request.content
    assert b'valid-test-png' in request.content
