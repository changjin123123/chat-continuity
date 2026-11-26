"""Deterministic synthetic text only. No private archive or model calls."""
import json
from pathlib import Path

from continuity.estimator import estimate_handoff, format_report


def samples():
    korean = "오늘 기록한 가상 회의에서는 자료를 먼저 검토하고 변경 사유를 남기기로 했습니다.\n"
    english = "Review the synthetic transcript and keep the unresolved questions with their evidence.\n"
    code = 'def remaining(limit: int, used: int):\n    return max(0, limit - used)  # 잔여량\n'
    payload = json.dumps({"상태": "검토 중", "enabled": True, "rows": [12, 34, 56], "note": "synthetic"}, ensure_ascii=False)
    return {"korean": korean * 20, "english": english * 20,
            "code": code * 20, "json": (payload + "\n") * 20,
            "mixed": (korean + english + code + payload + "\n") * 20,
            "unicode_edges": ("한글 漢字 café 👩🏽‍💻🙂 <|endoftext|> \\uD55C\r\n" * 20)}


def scenario():
    corpus = samples()
    original = json.dumps({"synthetic": True, "messages": [
        {"role": "user" if i % 2 == 0 else "assistant", "content": corpus["mixed"], "turn": i}
        for i in range(80)]}, ensure_ascii=False, indent=2)
    handoff = "# 합성 인계 요약\n" + corpus["mixed"]
    followup = "합성 확인 응답: 요구사항과 미완료 항목을 다시 확인했습니다.\n" + corpus["korean"]
    return original, handoff, followup


def main():
    original, handoff, followup = scenario()
    report = estimate_handoff([original], [handoff], [followup],
                              overhead_min=2000, overhead_max=8000,
                              next_turn_reserve=4000)
    print(format_report(report))
    root = Path("private/capacity-demo")
    root.mkdir(parents=True, exist_ok=True)
    # Demo always writes synthetic fixtures, never reads user files.
    for name, text in (("original.json", original), ("handoff.md", handoff), ("followup.txt", followup),
                       ("report.json", json.dumps(report, ensure_ascii=False, indent=2))):
        (root / name).write_text(text, encoding="utf-8")
    print("\n합성 예제 생성: private/capacity-demo (실제 대화 아님)")


if __name__ == "__main__":
    main()
