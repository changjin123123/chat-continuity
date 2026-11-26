"""Local text estimates, never native ChatGPT context telemetry."""
from __future__ import annotations

from datetime import datetime, timezone
from math import ceil

from .capacity import capacity_report
from .core import ContinuityError
from .tokenizers import load_encodings


DEFAULT_LIMITS = (32_000, 64_000, 128_000)


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ContinuityError(f"Invalid {name}")
    return value


def _texts(values, name, required=False):
    if not isinstance(values, (list, tuple)) or (required and not values):
        raise ContinuityError(f"{name} must be an explicit nonempty list of texts")
    if any(not isinstance(x, str) for x in values):
        raise ContinuityError(f"{name} must contain strings")
    for value in values:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContinuityError("Text contains invalid Unicode surrogates") from exc
    return values


def _heuristic(text):
    # Deliberately broad, uncalibrated sensitivity assumptions, not statistical
    # bounds. A run's true token count can fall outside this interval.
    low = high = 0.0
    for c in text:
        n = ord(c)
        if c.isspace():
            a, b = 0.125, 1.0
        elif c.isascii() and c.isalpha():
            a, b = 0.125, 0.5
        elif c.isascii() and c.isdigit():
            a, b = 1 / 3, 1.0
        elif c.isascii():
            a, b = 0.25, 1.0
        elif (0xAC00 <= n <= 0xD7A3 or 0x1100 <= n <= 0x11FF
              or 0x3130 <= n <= 0x318F or 0x3400 <= n <= 0x9FFF):
            a, b = 0.5, 3.0
        else:
            a, b = 0.5, float(len(c.encode("utf-8")))
        low += a
        high += b
    return {"low": ceil(low), "high": ceil(high)}


def _measure(texts, encodings):
    parts = []
    for text in texts:
        parts.append({
            "characters": len(text), "utf8_bytes": len(text.encode("utf-8")),
            "chars_div_4": ceil(len(text) / 4),
            "utf8_bytes_div_4": ceil(len(text.encode("utf-8")) / 4),
            "script_heuristic": _heuristic(text),
            # Token-like strings in transcripts are literal text, never controls.
            "bpe": {name: len(enc.encode_ordinary(text)) for name, enc in encodings.items()},
        })
    totals = {key: sum(p[key] for p in parts)
              for key in ("characters", "utf8_bytes", "chars_div_4", "utf8_bytes_div_4")}
    totals["script_heuristic"] = {
        side: sum(p["script_heuristic"][side] for p in parts) for side in ("low", "high")}
    totals["bpe"] = {name: sum(p["bpe"][name] for p in parts) for name in encodings}
    counts = list(totals["bpe"].values())
    totals["selected_token_range"] = (
        {"low": min(counts), "high": max(counts)} if counts else totals["script_heuristic"].copy())
    return {"segments": parts, "segment_count": len(parts), "totals": totals}


def estimate_handoff(original_texts, inserted_texts, followup_texts=(), *,
                     context_limits=DEFAULT_LIMITS, overhead_min=0, overhead_max=0,
                     next_turn_reserve=0, mode="auto", tokenizer_dir=None,
                     observed_at=None):
    """Count exact caller-selected text segments without loading or sending files.

    original_texts: archive inventory, NEVER added to current usage implicitly.
    inserted_texts: text the caller says remains in the new context now.
    followup_texts: retained explanations, messages, tool output after handoff.
    Compacted-away text and cumulative reading/billing totals must be excluded.
    """
    _texts(original_texts, "original_texts", True)
    _texts(inserted_texts, "inserted_texts", True)
    _texts(followup_texts, "followup_texts")
    if not isinstance(context_limits, (list, tuple)) or not context_limits:
        raise ContinuityError("Provide at least one assumed context limit")
    for limit in context_limits:
        _integer(limit, "context_limit", 1)
    _integer(overhead_min, "overhead_min")
    _integer(overhead_max, "overhead_max")
    _integer(next_turn_reserve, "next_turn_reserve")
    if overhead_min > overhead_max:
        raise ContinuityError("overhead_min must not exceed overhead_max")
    if mode not in ("auto", "bpe", "heuristic"):
        raise ContinuityError("Invalid tokenizer mode")
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ContinuityError("Invalid observed_at")
    encodings, unavailable = {}, None
    if mode != "heuristic":
        try:
            encodings = load_encodings(tokenizer_dir)
        except ContinuityError as exc:
            if mode == "bpe":
                raise
            unavailable = str(exc)
    original = _measure(original_texts, encodings)
    inserted = _measure(inserted_texts, encodings)
    followup = _measure(followup_texts, encodings)
    # Keep each tokenizer consistent across ALL retained segments; do not mix
    # the lowest/highest encoding independently for different segments.
    retained = _measure([*inserted_texts, *followup_texts], encodings)
    visible = retained["totals"]["selected_token_range"]
    used = {"low": visible["low"] + overhead_min,
            "high": visible["high"] + overhead_max}
    basis = "bpe_encoding_comparison" if encodings else "uncalibrated_script_heuristic"
    evidence = (f"Local text estimate; {basis}; caller-selected retained segments; "
                f"assumed overhead {overhead_min}..{overhead_max}; assumed context limit; "
                "no ChatGPT telemetry; not a confidence interval")
    scenarios = []
    for limit in dict.fromkeys(context_limits):
        reports = {side: capacity_report(limit, used[side], "estimated", evidence,
                                         observed_at, next_turn_reserve)
                   for side in ("low", "high")}
        remaining_low, remaining_high = max(0, limit - used["high"]), max(0, limit - used["low"])
        scenarios.append({
            "assumed_context_limit": limit,
            "used_tokens": used.copy(),
            "used_percent": {"low": reports["low"]["used_percent"], "high": reports["high"]["used_percent"]},
            "remaining_tokens": {"low": remaining_low, "high": remaining_high},
            "remaining_percent": {"low": round(remaining_low / limit * 100, 2),
                                  "high": round(remaining_high / limit * 100, 2)},
            "available_after_reserve": {"low": max(0, remaining_low - next_turn_reserve),
                                        "high": max(0, remaining_high - next_turn_reserve)},
            "shortfall_with_reserve": {"low": max(0, used["low"] + next_turn_reserve - limit),
                                       "high": max(0, used["high"] + next_turn_reserve - limit)},
            "overflow": "all" if used["low"] > limit else "possible" if used["high"] > limit else "none",
            "capacity_report_bounds": reports,
        })
    return {
        "schema_version": 1, "source": "estimated", "observed_at": observed_at,
        "native_chatgpt_capacity_known": False,
        "native_capacity_report": capacity_report(),
        "basis": basis, "bpe_unavailable_reason": unavailable,
        "range_is_confidence_interval": False,
        "original_archive": original, "inserted": inserted, "followup": followup,
        "retained_visible": retained, "assumed_overhead_tokens": {"low": overhead_min, "high": overhead_max},
        "estimated_used_tokens": used, "next_turn_reserve": next_turn_reserve,
        "scenarios": scenarios,
        "limitations": [
            "실제 ChatGPT 내부 사용량은 알 수 없음. 모든 한도와 잔여율은 가정에 따른 추정입니다.",
            "원문 전체는 보관량입니다. 사용량에는 inserted와 followup으로 지정한 현재 잔존 텍스트만 합산합니다.",
            "BPE 범위는 두 인코딩의 차이이며 정확도 보장/신뢰구간이 아닙니다. 문자 휴리스틱도 검증된 오차 범위가 아닙니다.",
            "기본 overhead=0은 숨겨진 지시문/메시지 포맷/도구/추론 토큰을 제외한다는 뜻입니다. 실제 0이라는 뜻이 아닙니다.",
            "이해 비용을 고정 배수로 더하지 않습니다. 남긴 응답/요약은 followup, 미확인 추가량은 overhead 가정으로만 반영합니다.",
            "이미지·음성·PDF 내용, 자동 압축/검색/잘림, 실제 삽입 여부와 중복 여부는 측정하지 않습니다.",
            "문자/4 및 UTF-8 바이트/4는 비교용입니다. ZIP 용량, 읽음 완료율, 누적 과금은 문맥 사용량이 아닙니다.",
            "각 입력은 별도 텍스트 구간으로 토큰화합니다. 실제 합쳐진 문자열이나 포맷이 다르면 결과가 바뀝니다.",
        ],
    }


def format_report(report):
    lines = ["새 문맥 용량 보조 추정 (실제 앱 계측 아님)",
             "실제 ChatGPT: 알 수 없음 / 100", f"추정 방식: {report['basis']}"]
    if report["bpe_unavailable_reason"]:
        lines.append("BPE 미사용: " + report["bpe_unavailable_reason"])
    for key, label in (("original_archive", "원문 전체(사용량에 자동 합산 안 함)"),
                       ("inserted", "현재 넣은 자료"), ("followup", "이후 남긴 응답/요약")):
        t = report[key]["totals"]
        r = t["selected_token_range"]
        lines.append(f"{label}: {t['characters']:,}자 / {t['utf8_bytes']:,} UTF-8 bytes / {r['low']:,}~{r['high']:,} tokens")
        if t["bpe"]:
            lines.append("  " + ", ".join(f"{k}={v:,}" for k, v in t["bpe"].items()))
    o = report["assumed_overhead_tokens"]
    lines.append(f"미확인 추가량 가정: {o['low']:,}~{o['high']:,} tokens / 다음 턴 예약: {report['next_turn_reserve']:,}")
    lines.append("한도 가정 | 사용률 추정 | 잔여율 추정 | 예약 후 여유(tokens)")
    for s in report["scenarios"]:
        u, r, a = s["used_percent"], s["remaining_percent"], s["available_after_reserve"]
        lines.append(f"{s['assumed_context_limit']:,} | {u['low']:.2f}~{u['high']:.2f}% | {r['low']:.2f}~{r['high']:.2f}% | {a['low']:,}~{a['high']:,} (초과: {s['overflow']})")
    lines.extend(report["limitations"])
    return "\n".join(lines)
