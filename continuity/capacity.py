"""Explicit context-budget reports; never infer native chat capacity from file size."""
from .core import ContinuityError, budget


def capacity_report(context_limit=None, used_tokens=None, source="unknown",
                    evidence="", observed_at="", next_turn_reserve=0):
    """Caller supplies an observation or estimate, not cumulative API billing usage."""
    if source not in ("unknown", "caller_reported", "estimated"):
        raise ContinuityError("Invalid usage source")
    for name, value in (("context_limit", context_limit), ("used_tokens", used_tokens)):
        if value is not None and (type(value) is not int or value < (1 if name == "context_limit" else 0)):
            raise ContinuityError(f"Invalid {name}")
    if type(next_turn_reserve) is not int or next_turn_reserve < 0:
        raise ContinuityError("Invalid next_turn_reserve")
    if not isinstance(evidence, str) or not isinstance(observed_at, str):
        raise ContinuityError("Evidence and observed_at must be strings")
    if source == "unknown" and (context_limit is not None or used_tokens is not None):
        raise ContinuityError("Values require caller_reported or estimated provenance")
    if source != "unknown" and (not evidence.strip() or not observed_at.strip()):
        raise ContinuityError("Measurements/estimates require evidence and observation time")
    known = context_limit is not None and used_tokens is not None and source != "unknown"
    result = {
        "metric": "current_context_tokens", "source": source,
        "context_limit": context_limit, "used_tokens": used_tokens,
        "evidence": evidence, "observed_at": observed_at,
        "used_percent": None, "remaining_percent": None,
        "display": "알 수 없음 / 100", "should_prepare_handoff": None,
        "native_chatgpt_capacity_known": False,
        "scope": "Caller-supplied current context budget; not native ChatGPT room capacity, file size, reading coverage or cumulative billed tokens",
    }
    if known:
        # Preserve overflow; a clamped 100% would hide insufficient context.
        percentage = round(used_tokens / context_limit * 100, 2)
        decision = budget(context_limit, used_tokens, next_turn_reserve)
        result.update(used_percent=percentage,
                      remaining_percent=round(max(0, 100 - percentage), 2),
                      display=f"{percentage:g} / 100 ({'추정' if source == 'estimated' else '호스트 제공값'})",
                      should_prepare_handoff=decision["should_prepare_handoff"],
                      remaining_tokens=decision["remaining_tokens"],
                      over_limit=used_tokens > context_limit)
    else:
        result["reason"] = "Current context usage and its applicable limit are not both available"
    return result
