import json
import subprocess

import pytest

from fitbit_report.reports.llm_runner import ClaudeCliError, ClaudeCliRunner


def test_runner_parses_json_without_calling_real_claude(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({
                "summary": "ok",
                "claims": [],
                "recommendations": [],
                "experiments": [],
                "confidence": "low",
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    draft = ClaudeCliRunner("sonnet", 1).generate("Русский промпт ☕")

    assert draft.summary == "ok"
    assert calls[0][0] == ["claude", "-p", "--model", "sonnet", "--output-format", "json", "--max-turns", "1"]
    assert calls[0][1]["input"] == "Русский промпт ☕"
    assert calls[0][1]["encoding"] == "utf-8"
    assert calls[0][1]["errors"] == "strict"


def test_runner_parses_claude_json_envelope(monkeypatch):
    draft_json = json.dumps({
        "summary": "ok",
        "claims": [],
        "recommendations": [],
        "experiments": [],
        "confidence": "low",
    })

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"type": "result", "result": draft_json}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert ClaudeCliRunner("sonnet", 1).generate("prompt").summary == "ok"


def test_runner_parses_fenced_json_inside_claude_envelope(monkeypatch):
    draft_json = json.dumps({
        "summary": "ok",
        "claims": [],
        "recommendations": [],
        "experiments": [],
        "confidence": "low",
    })

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"type": "result", "result": f"```json\n{draft_json}\n```"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert ClaudeCliRunner("sonnet", 1).generate("prompt").summary == "ok"


def test_runner_extracts_json_from_claude_explanation(monkeypatch):
    draft_json = json.dumps({
        "summary": "ok",
        "claims": [],
        "recommendations": [],
        "experiments": [],
        "confidence": "low",
    })

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({
                "type": "result",
                "result": f"Вот отчет:\n{draft_json}\nГотово.",
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert ClaudeCliRunner("sonnet", 1).generate("prompt").summary == "ok"


def test_runner_exposes_json_parse_error(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="{not valid json",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClaudeCliError, match="invalid JSON"):
        ClaudeCliRunner("sonnet", 1).generate("prompt")


def test_runner_exposes_report_schema_error(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"summary": "missing required fields"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClaudeCliError, match="invalid report schema"):
        ClaudeCliRunner("sonnet", 1).generate("prompt")


def test_runner_normalizes_common_claim_field_variants(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({
                "summary": "ok",
                "claims": [{
                    "type": "hypothesis",
                    "statement": "possible connection",
                    "evidence_count": 0,
                    "confidence": "none",
                    "alternative_explanations": ["another factor"],
                    "source_ids": [],
                }],
                "recommendations": [],
                "experiments": [],
                "confidence": "low",
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    claim = ClaudeCliRunner("sonnet", 1).generate("prompt").claims[0]

    assert claim.kind == "hypothesis"
    assert claim.confidence == "insufficient"
    assert claim.alternatives == ["another factor"]


def test_runner_flattens_structured_recommendations_and_experiments(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({
                "summary": "ok",
                "claims": [],
                "recommendations": [{
                    "action": "Keep today's workout light.",
                    "reason": "Sleep was below your baseline.",
                }],
                "experiments": [{
                    "hypothesis": "An earlier walk may improve sleep onset.",
                    "protocol": "Walk for 20 minutes after dinner.",
                    "duration": "Repeat for seven days.",
                    "measurement": "Compare sleep onset and next-day energy.",
                }],
                "confidence": "low",
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    draft = ClaudeCliRunner("sonnet", 1).generate("prompt")

    assert draft.recommendations == [
        "Keep today's workout light. — Sleep was below your baseline."
    ]
    assert draft.experiments == [
        "An earlier walk may improve sleep onset. — Walk for 20 minutes after dinner. — "
        "Repeat for seven days. — Compare sleep onset and next-day energy."
    ]


def test_runner_compacts_obvious_claim_flood(monkeypatch):
    claims = [
        {
            "statement": f"Записи показателя {index} за день нет.",
            "kind": "fact",
            "evidence_count": 1,
            "confidence": "high",
            "alternatives": [],
            "source_ids": [],
        }
        for index in range(9)
    ]
    claims += [
        {
            "statement": "Время сна резко сдвинулось относительно личного паттерна, что важнее обычного отклонения шагов.",
            "kind": "fact",
            "evidence_count": 14,
            "confidence": "high",
            "alternatives": [],
            "source_ids": [],
        },
        {
            "statement": "Есть повторяющаяся связь времени ужина со сном, но причинность пока не доказана.",
            "kind": "association",
            "evidence_count": 8,
            "confidence": "medium",
            "alternatives": [],
            "source_ids": [],
        },
    ]

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({
                "summary": "ok",
                "claims": claims,
                "recommendations": [f"Совет {index}" for index in range(8)],
                "experiments": [f"Эксперимент {index}" for index in range(5)],
                "confidence": "medium",
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    draft = ClaudeCliRunner("sonnet", 1).generate("prompt")

    assert len(draft.claims) <= 7
    assert len(draft.claims) >= 3
    assert any("сдвинулось" in claim.statement for claim in draft.claims)
    assert any(claim.kind == "association" for claim in draft.claims)
    assert len(draft.recommendations) == 5
    assert len(draft.experiments) == 3


def test_runner_accepts_typed_source_ids_from_health_context(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({
                "summary": "ok",
                "claims": [{
                    "statement": "Сон записан.",
                    "kind": "fact",
                    "evidence_count": 1,
                    "confidence": "high",
                    "alternatives": [],
                    "source_ids": ["health.sleep:2026-08-14", "event:1"],
                }],
                "recommendations": [],
                "experiments": [],
                "confidence": "high",
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    claim = ClaudeCliRunner("sonnet", 1).generate("prompt").claims[0]

    assert claim.source_ids == ["health.sleep:2026-08-14", "event:1"]


def test_runner_exposes_claude_error_when_process_fails(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=json.dumps({"type": "result", "is_error": True, "result": "Not authenticated"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(ClaudeCliError, match="Not authenticated"):
        ClaudeCliRunner("sonnet", 1).generate("prompt")


def test_runner_generates_json_from_an_image_with_read_tool(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({"summary": "обед"}),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    image_path = tmp_path / "meal.jpg"

    result = ClaudeCliRunner("sonnet", 1).generate_json(
        "Проанализируй фото еды.", image_path, max_turns=2
    )

    assert result == {"summary": "обед"}
    assert calls[0][0] == [
        "claude",
        "-p",
        "--model",
        "sonnet",
        "--output-format",
        "json",
        "--max-turns",
        "2",
        "--allowedTools",
        "Read",
        "--add-dir",
        str(tmp_path),
    ]
    assert str(image_path) in calls[0][1]["input"]


def test_runner_generates_plain_text_for_a_user_question(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="Готовый персональный ответ.",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    image_path = tmp_path / "sleep.png"

    answer = ClaudeCliRunner("claude-opus-5", 1).generate_text(
        "Что со сном?", image_paths=[image_path]
    )

    assert answer == "Готовый персональный ответ."
    assert "--output-format" not in calls[0][0]
    assert calls[0][0][-4:] == ["--allowedTools", "Read", "--add-dir", str(tmp_path)]
    assert str(image_path) in calls[0][1]["input"]


def test_runner_records_real_usage_and_calculates_api_equivalent_cost(monkeypatch):
    recorded = []

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps({
                "result": {"answer": "ok"},
                "usage": {
                    "input_tokens": 1_000,
                    "output_tokens": 250,
                    "cache_read_input_tokens": 500,
                },
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = ClaudeCliRunner(
        "sonnet",
        1,
        usage_recorder=lambda operation, model, usage, success: recorded.append(
            (operation, model, usage, success)
        ),
        operation="question",
    ).generate_json("prompt")

    assert result == {"answer": "ok"}
    assert len(recorded) == 1
    operation, model, usage, success = recorded[0]
    assert (operation, model, success) == ("question", "sonnet", True)
    assert usage["input_tokens"] == 1_000
    assert usage["output_tokens"] == 250
    assert usage["cache_read_input_tokens"] == 500
    assert usage["estimated"] is False
    assert usage["estimated_cost_usd"] == pytest.approx(0.0046)
