# 새 방 문맥 용량 보조 추정기

이 도구는 로컬 텍스트를 세어 **가정한 문맥 한도별 잔여량**을 계산합니다.
실제 ChatGPT 내부 사용량, 실제 문맥 한도, 파일 검색/압축 후 남은 상태를 읽지 않습니다.
`capacity_report()`의 미확인 표시는 그대로 유지하며, 별도 추정표만 제공합니다.

## Windows에서 바로 실행

1. ZIP을 모두 압축 해제합니다. Python 3.10 이상이 필요합니다.
2. 폴더 안의 `run_capacity_demo.cmd`를 두 번 클릭하면 **합성 대화**로 실행됩니다.
   Python이 없으면 설치 안내를 표시하며, 자동으로 설치하지 않습니다.
3. 기본 기능은 외부 패키지 없이 실행됩니다. `auto` 모드는 BPE 사용 조건이 갖춰지면
   BPE를 쓰고, 그렇지 않으면 문자 종류별 휴리스틱과 그 사유를 표시합니다.
4. BPE 비교를 쓰려면 PowerShell에서 압축 해제한 폴더로 이동해 한 번 설치합니다.

```powershell
py -3 -m pip install tiktoken==0.12.0
```

다운로드 ZIP에는 검증된 공개 토큰 사전 두 개가 들어 있습니다.
GitHub 소스에서 시작했거나 사전이 없으면 다음 준비 명령을 한 번 실행하세요.
이 명령은 공개 사전만 내려받고, 대화 입력 인수를 받지 않습니다.

```powershell
py -3 -m continuity prepare-tokenizers
py -3 -m examples.capacity_demo
```

설치/사전 준비 후 실제 계산은 인터넷 연결 없이 실행할 수 있습니다. API 키가 필요하지 않습니다.
`py`가 없고 `python`이 설치되어 있으면 명령의 `py -3`을 `python`으로 바꾸세요.

## 내 자료 계산

합성 데모가 만든 파일로 다음 명령을 먼저 연습할 수 있습니다.

```powershell
py -3 -m continuity estimate-capacity --original "private/capacity-demo/original.json" --inserted "private/capacity-demo/handoff.md" --followup "private/capacity-demo/followup.txt" --limits 32000 64000 128000 --overhead 2000 8000 --reserve 4000 --mode bpe --output "capacity-report.json"
```

실제 사용할 때에는 파일 경로와 가정 수치를 바꾸세요. 결과 파일이 이미 있으면 새 이름을
사용해야 합니다. 입력·기존 출력 파일을 덮어쓰지 않습니다.

| 입력 | 의미 | 현재 사용량에 합산 |
|---|---|---|
| `--original` | 이전 방 전체 원문 TXT/MD/JSON/코드. 보관량 비교용 | 자동 합산 안 함 |
| `--inserted` | 새 문맥에 현재 남아 있다고 확인/가정한 원문 구간·인계 요약·지시문 | 합산 |
| `--followup` | 읽은 뒤 남긴 요약·설명·확인 응답·도구 결과 | 합산 |
| `--overhead MIN MAX` | 숨겨진 지시문·포맷·도구 정의·추론 등 미확인 추가량 가정 | 범위로 합산 |
| `--reserve` | 앞으로 한 턴에 쓸 예산 | 사용량과 별도로 예약 |
| `--limits` | 여러 문맥 한도 가정 | 비율 계산의 분모 |

**32,000 / 64,000 / 128,000은 비교를 위한 예시입니다. 현재 모델·플랜·ChatGPT 앱의
확인된 한도가 아닙니다.** 기본 overhead=0은 알 수 없는 추가량을 계산에서 뺐다는 뜻이며,
실제로 없다는 뜻이 아닙니다. 예제의 2,000~8,000도 측정치나 권장 안전 여유가 아닙니다.

여러 파일은 `--inserted "a.md" --inserted "b.json"`처럼 반복합니다.
같은 파일을 두 번 지정하면 두 번 계산합니다. 이는 실제 문맥에 반복 인용된 자료를
임의로 제거하지 않기 위한 동작입니다. 원문 전체를 실제 넣었다면
`--original "원문.json" --inserted "원문.json"`으로 지정하세요.

자료가 얼마나 삽입됐는지 모르면 `요약만`, `요약+발췌`, `원문 전체+요약`을 각각 계산하세요.
첨부 파일 전체, 과거에 읽은 모든 구간, 현재 문맥에 남은 구간은 서로 다를 수 있습니다.
현재 남아 있지 않은 구간의 누적 읽기 토큰이나 누적 API 과금 토큰을 더하면 안 됩니다.

UTF-8 및 UTF-8 BOM 파일을 지원합니다. CRLF와 공백, JSON의 들여쓰기/이스케이프는
그대로 계산하고 선두 BOM만 제거합니다. 원본 파일 바이트와 실제 텍스트 UTF-8 바이트는
별도로 보고합니다. JSON은 파싱·분기 선택·메타데이터 제거 없이 **입력된 문자열 전체**를
셉니다. 실제 모델에 JSON의 내용만 전달했다면 그 내용만 추출한 별도 파일을 지정해야 합니다.
ZIP/PDF/이미지는 지원하지 않습니다. 파일 크기를 토큰 수로 변환하지 않습니다.

## 계산 방법과 해석

```
현재 사용량 추정 = 현재 넣은 텍스트 + 이후 남긴 텍스트 + 미확인 추가량 가정
잔여량 추정 = max(0, 한도 가정 - 현재 사용량 추정)
예약 후 여유 = max(0, 잔여량 추정 - 다음 턴 예약)
```

이해에는 고정된 '원문 토큰의 몇 배'가 추가된다는 공식을 사용하지 않습니다.
실제로 생성되어 현재 남은 요약·응답은 셀 수 있지만 숨겨진 추론 상태는 이 도구로
측정할 수 없습니다. 생각에 든 시간이나 처리한 누적 토큰과 현재 문맥 점유는 다릅니다.

토큰화 비교는 네 가지를 보여줍니다.

- `chars_div_4`: 유니코드 문자 수/4. 한국어·코드·JSON에서 부정확할 수 있는 비교용 값.
- `utf8_bytes_div_4`: UTF-8 텍스트 바이트/4. 압축 파일 바이트가 아니며 비교용 값.
- `script_heuristic`: 영문·숫자·기호·한글/한자·그 외 문자 가중치의 넓은 범위.
  검증된 오차 범위가 아닙니다. BPE가 없을 때만 잔여량 계산에 사용합니다.
- `cl100k_base` / `o200k_base`: 공개 BPE 사전으로 **주어진 텍스트**의 토큰 수를 계산.
  두 값을 작고 큰 순으로 표시합니다. 실제 ChatGPT가 이 인코딩을 쓴다고 단정하지 않습니다.

BPE 범위는 두 인코딩의 차이를 보여주는 민감도 범위입니다. 95% 신뢰구간도 실제 앱
사용량의 확정된 상·하한도 아닙니다. 실제 값은 범위를 벗어날 수 있습니다.

휴리스틱 가중치(문자당 토큰 하한~상한 가정)는 공백 0.125~1, ASCII 영문 0.125~0.5,
ASCII 숫자 1/3~1, ASCII 기호 0.25~1, 한글/한자 0.5~3,
기타 문자 0.5~해당 문자의 UTF-8 바이트 수입니다. 합계는 구간별 올림합니다.
합성 표본을 확인해 정한 설계값이며 언어별 대표 말뭉치로 통계 보정한 값이 아닙니다.

각 인코딩으로 모든 현재 구간을 합산한 뒤 범위를 정합니다. 구간마다 유리한 인코딩을
골라 섞지 않습니다. 각 파일은 별도 구간으로 셉니다. 실제 결합 문자열이나 메시지 포맷이
다르면 수치가 바뀔 수 있습니다. `<|endoftext|>` 같은 원문 문자열은 일반 텍스트로 셉니다.

한도를 넘으면 사용률 100% 초과를 유지합니다. 잔여량 0과 함께 `overflow` 및 다음 턴
예약을 포함한 부족량을 표시합니다. 출력의 `capacity_report_bounds.low/high`는
사용량 하한/상한이며, 잔여율은 이 순서가 반대입니다.

## Python / 기존 capacity_report 연결

```python
from continuity.estimator import estimate_handoff

r = estimate_handoff(
    original_texts=["전체 원문"],
    inserted_texts=["현재 넣은 인계 요약"],
    followup_texts=["읽고 난 뒤 남긴 확인 응답"],
    context_limits=[32000, 64000, 128000],
    overhead_min=2000, overhead_max=8000,
    next_turn_reserve=4000, mode="auto",
)
for scenario in r["scenarios"]:
    low = scenario["capacity_report_bounds"]["low"]
    high = scenario["capacity_report_bounds"]["high"]
    # 두 객체 모두 기존 capacity_report(..., source="estimated") 결과입니다.
    print(low["used_percent"], high["used_percent"])
```

기존 `capacity_report` 함수와 MCP 스키마는 바꾸지 않았습니다. 추정기의 각 범위 끝점을
기존 함수에 전달해 `source=estimated`, 근거, 계산 시각을 기록합니다.
`native_capacity_report`는 계속 미확인으로 남습니다. 이 결과로 ChatGPT 방을 생성하거나
`prepare_handoff`를 자동 실행하지 않습니다.

## 개인정보와 검증

실제 계산 경로에는 업로드, 모델/API 호출, 원격 토큰화가 없습니다. 원문 텍스트,
파일명, 파일 경로를 결과 JSON에 넣지 않으며 개수·문자·바이트·토큰만 기록합니다.
결과 통계도 자료에 관한 정보이므로 원문과 함께 로컬 `private/`에 두는 것을 권합니다.
기존 MCP의 원문 읽기 도구를 AI 서비스에 연결하는 것은 별개의 데이터 전달입니다.
이 추정기 사용에 MCP 연결은 필요하지 않습니다.

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m examples.capacity_benchmark
```

합성 자료 비교와 실제 실행 결과: [CAPACITY_VALIDATION.md](CAPACITY_VALIDATION.md).
Windows 전용 실행기는 제공하지만 개발 환경의 로컬 검증 OS는 Linux입니다.
Windows 호환성은 별도 GitHub Actions 작업으로도 검사하도록 구성했습니다.

공식 참고 자료:
- [OpenAI tiktoken](https://github.com/openai/tiktoken)
- [OpenAI 토큰 계산 예제](https://developers.openai.com/cookbook/examples/how_to_count_tokens_with_tiktoken)
- [인코딩 정의와 공개 사전 해시](https://github.com/openai/tiktoken/blob/0.12.0/tiktoken_ext/openai_public.py)
