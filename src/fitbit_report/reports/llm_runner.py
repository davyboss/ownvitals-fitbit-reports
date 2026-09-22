import json
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from fitbit_report.reports.schemas import ReportDraft


class ClaudeCliError(RuntimeError):
    pass


_MAX_REPORT_CLAIMS = 7
_MAX_REPORT_RECOMMENDATIONS = 5
_MAX_REPORT_EXPERIMENTS = 3


def _claim_priority(claim: dict[str, object]) -> float:
    statement = str(claim.get("statement", "")).casefold()
    kind = str(claim.get("kind", claim.get("type", "fact"))).casefold()
    confidence = str(claim.get("confidence", "insufficient")).casefold()
    score = {"association": 5.0, "hypothesis": 4.0, "fact": 1.0}.get(kind, 0.0)
    score += {"high": 2.0, "medium": 1.0, "low": 0.25}.get(confidence, -1.0)
    score += min(2.0, max(0.0, int(claim.get("evidence_count", 0) or 0) / 5.0))

    meaningful_signals = (
        "связ",
        "паттерн",
        "тренд",
        "сдвиг",
        "аномал",
        "двойной учёт",
        "профицит",
        "после",
        "не согласуется",
        "важнее",
        "повторя",
    )
    obvious_inventory = (
        "записей нет",
        "записи нет",
        "нет данных",
        "не зафиксирован",
        "не зафиксировано",
        "нет трениров",
        "веса нет",
        "нельзя оценить",
        "отсутствует",
    )
    if any(signal in statement for signal in meaningful_signals):
        score += 2.5
    if any(signal in statement for signal in obvious_inventory):
        score -= 2.5
    if len(statement) < 80:
        score -= 0.5
    return score


def _same_claim(left: str, right: str) -> bool:
    left = " ".join(left.casefold().split())
    right = " ".join(right.casefold().split())
    if left == right:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.82


def _compact_claims(claims: list[object]) -> list[object]:
    valid = [claim for claim in claims if isinstance(claim, dict)]
    if len(valid) <= _MAX_REPORT_CLAIMS:
        return claims

    ranked = sorted(
        enumerate(valid),
        key=lambda item: (_claim_priority(item[1]), -item[0]),
        reverse=True,
    )
    selected: list[tuple[int, dict[str, object]]] = []
    for index, claim in ranked:
        statement = str(claim.get("statement", ""))
        if any(_same_claim(statement, str(item.get("statement", ""))) for _, item in selected):
            continue
        selected.append((index, claim))
        if len(selected) >= _MAX_REPORT_CLAIMS:
            break
    return [claim for _, claim in sorted(selected, key=lambda item: item[0])]


def _stringify_text_item(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        parts = [_stringify_text_item(value) for value in item.values()]
    elif isinstance(item, (list, tuple)):
        parts = [_stringify_text_item(value) for value in item]
    elif item is None:
        return ""
    else:
        return str(item).strip()

    result: list[str] = []
    normalized_seen: set[str] = set()
    for part in parts:
        key = " ".join(part.casefold().split())
        if not key or key in normalized_seen:
            continue
        normalized_seen.add(key)
        result.append(part)
    return " — ".join(result)


def _compact_text_items(items: object, limit: int) -> object:
    if not isinstance(items, list):
        return items
    result: list[str] = []
    normalized_seen: set[str] = set()
    for item in items:
        text = _stringify_text_item(item)
        key = " ".join(text.casefold().split())
        if not key or key in normalized_seen:
            continue
        normalized_seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _as_non_negative_int(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _extract_usage(payload: object) -> dict[str, int]:
    """Extract token counters from the different Claude CLI JSON envelopes."""
    counters = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    aliases = {
        "input_tokens": {"input_tokens", "inputtokens", "prompt_tokens", "prompttokens"},
        "output_tokens": {"output_tokens", "outputtokens", "completion_tokens", "completiontokens"},
        "cache_read_input_tokens": {"cache_read_input_tokens", "cachereadinputtokens"},
        "cache_creation_input_tokens": {"cache_creation_input_tokens", "cachecreationinputtokens"},
    }

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = str(key).lower().replace("-", "_")
                compact_key = normalized_key.replace("_", "")
                for counter, names in aliases.items():
                    if normalized_key in names or compact_key in names:
                        counters[counter] = max(counters[counter], _as_non_negative_int(item))
                        break
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return counters


def _estimate_tokens(text: str) -> int:
    # Fallback for CLI versions that do not expose usage metadata.
    return max(1, len(text) // 4) if text else 0


def _failure_detail(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stderr or result.stdout or "").strip()
    if not text:
        return f"exit code {result.returncode}"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:1000]
    if isinstance(payload, dict):
        for key in ("error", "message", "result"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:1000]
            if isinstance(value, dict):
                message = value.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()[:1000]
    return text[:1000]


def _parse_json_text(text: str) -> object:
    normalized = text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()

    try:
        return json.loads(normalized)
    except json.JSONDecodeError as original_error:
        # Claude sometimes adds a short sentence before or after the JSON,
        # despite the prompt asking for JSON only.
        start = normalized.find("{")
        end = normalized.rfind("}")
        if start < 0 or end <= start:
            raise original_error
        try:
            return json.loads(normalized[start:end + 1])
        except json.JSONDecodeError:
            raise original_error


def _parse_report_payload(stdout: str) -> object:
    payload: object = _parse_json_text(stdout)
    while isinstance(payload, dict) and "result" in payload and "summary" not in payload:
        payload = payload["result"]
        if isinstance(payload, str):
            payload = _parse_json_text(payload)
    return payload


def _normalize_report_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    if normalized.get("confidence") == "none":
        normalized["confidence"] = "insufficient"

    claims = normalized.get("claims")
    if isinstance(claims, list):
        normalized_claims = []
        for claim in claims:
            if not isinstance(claim, dict):
                normalized_claims.append(claim)
                continue
            normalized_claim = dict(claim)
            if "kind" not in normalized_claim and "type" in normalized_claim:
                normalized_claim["kind"] = normalized_claim["type"]
            if (
                "alternatives" not in normalized_claim
                and "alternative_explanations" in normalized_claim
            ):
                normalized_claim["alternatives"] = normalized_claim[
                    "alternative_explanations"
                ]
            if normalized_claim.get("confidence") == "none":
                normalized_claim["confidence"] = "insufficient"
            normalized_claims.append(normalized_claim)
        normalized["claims"] = _compact_claims(normalized_claims)

    normalized["recommendations"] = _compact_text_items(
        normalized.get("recommendations"), _MAX_REPORT_RECOMMENDATIONS
    )
    normalized["experiments"] = _compact_text_items(
        normalized.get("experiments"), _MAX_REPORT_EXPERIMENTS
    )

    return normalized


class ClaudeCliRunner:
    def __init__(
        self,
        model: str,
        max_turns: int = 1,
        usage_recorder: Callable[[str, str, dict[str, object], bool], None] | None = None,
        operation: str = "claude",
        input_price_per_million_usd: float = 2.0,
        output_price_per_million_usd: float = 10.0,
        cache_read_price_per_million_usd: float = 0.20,
        cache_creation_price_per_million_usd: float = 2.50,
    ):
        self.model = model
        self.max_turns = max_turns
        self.usage_recorder = usage_recorder
        self.operation = operation
        self.input_price_per_million_usd = input_price_per_million_usd
        self.output_price_per_million_usd = output_price_per_million_usd
        self.cache_read_price_per_million_usd = cache_read_price_per_million_usd
        self.cache_creation_price_per_million_usd = cache_creation_price_per_million_usd

    def _record_usage(self, prompt: str, stdout: str, success: bool) -> None:
        if self.usage_recorder is None:
            return
        try:
            payload = _parse_json_text(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        usage = _extract_usage(payload)
        estimated = False
        if usage["input_tokens"] == 0:
            usage["input_tokens"] = _estimate_tokens(prompt)
            estimated = True
        if usage["output_tokens"] == 0 and stdout:
            usage["output_tokens"] = _estimate_tokens(stdout)
            estimated = True
        usage_payload: dict[str, object] = {
            **usage,
            "estimated": estimated,
            "estimated_cost_usd": (
                usage["input_tokens"] * self.input_price_per_million_usd
                + usage["output_tokens"] * self.output_price_per_million_usd
                + usage["cache_read_input_tokens"] * self.cache_read_price_per_million_usd
                + usage["cache_creation_input_tokens"] * self.cache_creation_price_per_million_usd
            ) / 1_000_000,
        }
        try:
            self.usage_recorder(self.operation, self.model, usage_payload, success)
        except Exception:
            # Accounting must never make an otherwise successful bot request fail.
            pass

    def generate(self, prompt: str) -> ReportDraft:
        args = [
            "claude", "-p", "--model", self.model,
            "--output-format", "json", "--max-turns", str(self.max_turns),
        ]
        try:
            result = subprocess.run(
                args,
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="strict",
                capture_output=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCliError("Claude CLI timed out") from exc
        self._record_usage(prompt, result.stdout, result.returncode == 0)
        if result.returncode != 0:
            raise ClaudeCliError(
                f"Claude CLI failed (exit code {result.returncode}): {_failure_detail(result)}"
            )
        try:
            payload = _parse_report_payload(result.stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeCliError(
                f"Claude returned invalid JSON: {exc.msg} at position {exc.pos}"
            ) from exc
        try:
            return ReportDraft.model_validate(_normalize_report_payload(payload))
        except ValueError as exc:
            raise ClaudeCliError(
                f"Claude returned JSON with invalid report schema: {exc}"
            ) from exc

    def generate_json(
        self,
        prompt: str,
        image_path: Path | None = None,
        image_paths: list[Path] | None = None,
        max_turns: int | None = None,
    ) -> object:
        turns = max_turns if max_turns is not None else self.max_turns
        args = [
            "claude", "-p", "--model", self.model,
            "--output-format", "json", "--max-turns", str(turns),
        ]
        input_text = prompt
        paths = [Path(item) for item in (image_paths or [])]
        if image_path is not None:
            paths.insert(0, Path(image_path))
        if paths:
            args.extend([
                "--allowedTools", "Read",
            ])
            for parent in dict.fromkeys(str(path.parent) for path in paths):
                args.extend(["--add-dir", parent])
            image_instructions = "\n".join(
                f"- Read the image with the Read tool at this path: {path}"
                for path in paths
            )
            input_text = f"{prompt}\n\nImages to analyze:\n{image_instructions}"
        try:
            result = subprocess.run(
                args,
                input=input_text,
                text=True,
                encoding="utf-8",
                errors="strict",
                capture_output=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCliError("Claude CLI timed out") from exc
        self._record_usage(input_text, result.stdout, result.returncode == 0)
        if result.returncode != 0:
            raise ClaudeCliError(
                f"Claude CLI failed (exit code {result.returncode}): {_failure_detail(result)}"
            )
        try:
            return _parse_report_payload(result.stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeCliError(
                f"Claude returned invalid JSON: {exc.msg} at position {exc.pos}"
            ) from exc

    def generate_text(
        self,
        prompt: str,
        image_paths: list[Path] | None = None,
        max_turns: int | None = None,
    ) -> str:
        """Generate a user-facing answer without imposing the report JSON envelope."""
        turns = max_turns if max_turns is not None else self.max_turns
        args = ["claude", "-p", "--model", self.model, "--max-turns", str(turns)]
        input_text = prompt
        paths = [Path(item) for item in (image_paths or [])]
        if paths:
            args.extend(["--allowedTools", "Read"])
            for parent in dict.fromkeys(str(path.parent) for path in paths):
                args.extend(["--add-dir", parent])
            image_instructions = "\n".join(
                f"- Read the image with the Read tool at this path: {path}"
                for path in paths
            )
            input_text = f"{prompt}\n\nImages to analyze:\n{image_instructions}"
        try:
            result = subprocess.run(
                args,
                input=input_text,
                text=True,
                encoding="utf-8",
                errors="strict",
                capture_output=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCliError("Claude CLI timed out") from exc
        self._record_usage(input_text, result.stdout, result.returncode == 0)
        if result.returncode != 0:
            raise ClaudeCliError(
                f"Claude CLI failed (exit code {result.returncode}): {_failure_detail(result)}"
            )
        answer = result.stdout.strip()
        if not answer:
            raise ClaudeCliError(
                "Claude CLI returned an empty response: " + _failure_detail(result)
            )
        return answer
