"""Print reproducible synthetic tokenizer comparisons; no network access."""
from continuity.estimator import estimate_handoff
from .capacity_demo import samples, scenario


def main():
    print("| 합성 자료 | 문자/4 | UTF-8 bytes/4 | 휴리스틱 범위 | cl100k | o200k | 문자/4 대 o200k 차이 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for name, text in samples().items():
        t = estimate_handoff([text], [text], mode="bpe")["inserted"]["totals"]
        h, b = t["script_heuristic"], t["bpe"]
        error = (t["chars_div_4"] / b["o200k_base"] - 1) * 100
        print(f"| {name} | {t['chars_div_4']} | {t['utf8_bytes_div_4']} | {h['low']}~{h['high']} | {b['cl100k_base']} | {b['o200k_base']} | {error:+.1f}% |")
    original, handoff, followup = scenario()
    from continuity.estimator import format_report
    print("\n" + format_report(estimate_handoff([original], [handoff], [followup],
          mode="bpe", overhead_min=2000, overhead_max=8000, next_turn_reserve=4000)))


if __name__ == "__main__":
    main()
