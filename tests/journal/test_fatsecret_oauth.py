from datetime import date

from fitbit_report.journal.fatsecret_oauth import FatSecretOAuthClient


class FakeResponse:
    def __init__(self, text="", payload=None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, params=None, headers=None):
        self.calls.append((method, url, params, headers))
        return self.responses.pop(0)


def test_fatsecret_oauth_can_start_complete_and_read_one_day():
    http = FakeHttp([
        FakeResponse("oauth_token=request&oauth_token_secret=request-secret"),
        FakeResponse("oauth_token=access&oauth_token_secret=access-secret"),
        FakeResponse(payload={
            "food_entries": {
                "food_entry": {
                    "meal": "Breakfast",
                    "food_entry_name": "Овсянка",
                    "food_entry_description": "60 г овсянки",
                    "calories": "220",
                    "protein": "7.2",
                    "carbohydrate": "36.4",
                    "fat": "4.1",
                }
            }
        }),
    ])
    client = FatSecretOAuthClient("consumer", "secret", http=http)

    started = client.start_authorization()
    access = client.complete_authorization(
        started.request_token, started.request_token_secret, "verifier"
    )
    entries, _ = client.fetch_food_diary(
        date(2026, 8, 28), access.token, access.secret
    )

    assert started.authorization_url.endswith("oauth_token=request")
    assert access.token == "access"
    assert entries[0].meal_type == "breakfast"
    assert entries[0].calories == 220
    assert entries[0].protein_g == 7.2
    assert http.calls[0][0] == "GET"
    assert http.calls[0][2]["oauth_callback"] == "oob"
    assert "oauth_signature" in http.calls[0][2]
    assert http.calls[0][3] == {}
    assert http.calls[1][2]["oauth_verifier"] == "verifier"
    assert "oauth_signature" in http.calls[1][2]
    assert http.calls[2][2]["format"] == "json"
    assert "oauth_signature" in http.calls[2][3]["Authorization"]
