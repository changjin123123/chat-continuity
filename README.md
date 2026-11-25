# Chat Continuity — 원문 기반 AI 대화 이어받기

원문을 보존하고, 새 AI 세션이 모든 원문 구간을 처리했는지 기록하며,
결정 변경·취소·미완료 작업에 대한 질문을 통과한 뒤 내부 세션을 전환하는 **실행 가능한 v0.1**입니다.

**ChatGPT 앱의 모든 방을 자동 감시하거나 새 ChatGPT 방을 만드는 제품은 아직 아닙니다.**
이 저장소는 로컬 MCP 도구 서버와 CLI입니다. 별도 AI 클라이언트/세션 관리자가 연결해야 합니다.
모델의 지식이나 가중치를 바꾸지 않으며, 완벽한 이해·기억을 보장하지 않습니다.

공개 코드 저장소: https://github.com/changjin123123/chat-continuity

## 구현 상태

| 기능 | v0.1 |
|---|---|
| ChatGPT 내보내기 JSON 가져오기 | 구현. `mapping` 원본의 모든 분기·알 수 없는 필드 보존 |
| 일반 `messages` JSON 가져오기 | 구현 |
| 원본 바이트 복원·SHA-256 검증 | 구현 |
| 대화방별 수정 이력·스냅샷 | 구현. 같은 대화 id의 변경본도 보관 |
| 전체 원문 분할 및 세션별 처리 확인 | 구현. 읽음 확인은 이해도 증명이 아님 |
| 결정·취소·미완료 기록과 원문 인용 연결 | 구현. 해석은 연결된 AI가 작성 |
| 원문 검색·재조회 | 구현. 한국어 포함 문자 그대로 검색, 의미 검색은 미구현 |
| 잔여 5% 또는 다음 응답 여유 부족 시 전환 준비 | 구현. 호스트가 실제 토큰 사용량을 제공해야 함 |
| 조건 충족 후 내부 세션 활성화 | 구현. 누락·실패·오래된 원문·선행 세션 충돌 시 차단 |
| 첨부파일 바이트 보존 | 구현. 첨부 목록은 운영자가 매핑 |
| 이미지·음성·PDF 내용 이해 검증 | 미구현. 첨부가 발견되면 자동 활성화 차단 |
| 현재 ChatGPT 앱과 자동 동기화·새 방 생성 | 미구현 |
| 원문을 읽은 AI의 숨겨진 사고 상태 이식 | 구현하지 않으며 가능하다고 주장하지 않음 |

## 바로 실행 — Windows / macOS / Linux

Python 3.10 이상. 실행에 외부 패키지나 API 키는 필요 없습니다.
Python을 설치하고 압축을 해제한 폴더에서 실행하세요. Windows에서 `python`이 없으면 `py`로 바꾸세요.

Git을 사용하는 경우:

```bash
git clone https://github.com/changjin123123/chat-continuity.git
cd chat-continuity
```

```bash
python -m unittest discover -s tests -v
python -m examples.demo
```

데모는 **가상 대화·정해진 답을 사용한 오프라인 프로토콜 시뮬레이션**입니다.
실제 AI의 이해도 평가나 ChatGPT 앱 전환 성공으로 해석하면 안 됩니다. 유료 API 호출은 없습니다.

## 실제 원문 준비

1. ChatGPT에서 받은 내보내기 ZIP은 사용자가 로컬에서 해제합니다.
2. 대화 JSON 파일을 `imports/`에 두세요. `imports/`는 Git에서 제외됩니다.
3. 필요한 대화만 분리한 JSON을 프로젝트별로 가져오세요. 전체 계정 파일을 한 프로젝트에 넣으면
   그 파일의 모든 대화가 해당 프로젝트 범위가 됩니다. 프로그램이 제목으로 프로젝트를 추측하지 않습니다.
4. 여러 JSON 파일이면 같은 프로젝트로 순서대로 가져올 수 있습니다. 같은 대화 id는 마지막 가져오기를 현재 버전으로 사용합니다.
   오래된 파일을 나중에 가져오면 현재 버전도 과거 상태가 되므로 내보내기 시점을 확인하세요.
5. 실제 원문을 받지 못한 대화, 삭제된 대화, 내보내기에 빠진 첨부파일은 복구했다고 주장하지 않습니다.

```bash
python -m continuity import demo examples/conversations.json
python -m continuity list
python -m continuity snapshot demo --order demo-room-1 demo-room-2
```

마지막 명령이 `snapshot` ID를 출력합니다. 원문은 기본 `.continuity/archive.sqlite3`에 보관됩니다.
`--db`는 모든 명령에서 하위 명령 앞에 둘 수 있습니다.

```bash
python -m continuity --db private/work.sqlite3 import my-project imports/conversations.json
```

원본 파일을 바이트 그대로 복원할 때는 가져오기에서 받은 `source_sha256`을 사용합니다.
복원 대상 파일이 이미 있으면 덮어쓰지 않습니다.

```bash
python -m continuity export-source SOURCE_SHA restored.json
```

## MCP 지원 AI 클라이언트 연결

다음은 **로컬 stdio MCP를 지원하는 클라이언트용 예시**입니다.
현재 ChatGPT iOS 앱 설정에 그대로 붙여 넣어 동작한다는 의미가 아닙니다.
Python 패키지를 로컬 환경에 설치하면 어떤 작업 디렉터리에서도 모듈을 찾을 수 있습니다.

```bash
python -m pip install -e .
```

```json
{
  "mcpServers": {
    "chat-continuity": {
      "command": "python",
      "args": ["-m", "continuity", "--db", "C:/Users/YOU/chat-continuity/.continuity/archive.sqlite3", "mcp"]
    }
  }
}
```

실제 Python 실행 파일과 DB 절대 경로를 넣으세요. 전체 디스크 파일을 읽는 도구는 노출하지 않습니다.
원문 가져오기·첨부파일 등록·시험 정답 등록은 로컬 운영자 CLI로만 제공합니다.
연결된 AI 서비스에는 도구로 요청한 원문이 전달됩니다. 서비스 연결 전에 데이터 범위를 확인하세요.

### 새 AI에게 전달할 지시문

`docs/READER_INSTRUCTIONS.md`를 사용하세요. 새 AI 문맥에는 반드시 새 reader session을 만듭니다.
같은 세션의 MCP 연결을 재연결하면 처리 위치가 유지됩니다. **모델 문맥이 초기화됐다면 연결 재개와 달리 새 reader session이 필요합니다.**
처리 기록이 있다고 새 AI가 이미 읽었다고 간주하면 안 됩니다.

실제 도구 흐름:

1. `new_session(snapshot)` 또는 호스트가 준비한 새 `target_session`을 사용합니다.
2. `read_next(session)`로 다음 **원문**을 읽습니다. 모든 필드와 대화 분기를 처리합니다.
3. 반환된 위치·해시·수신 토큰으로 `acknowledge`를 호출합니다.
4. 원문 인용을 근거로 `remember`에 결정·취소·미완료·불확실 사항을 남깁니다.
5. `done=true`가 될 때까지 반복합니다. 검색만 사용해서 전체 읽기를 대체하지 않습니다.
6. `questions`에 대해 `answer`로 응답하고 `status`를 확인합니다.
7. `activate`는 내부 활성 세션 포인터만 바꿉니다. 실제 새 방 생성은 호스트 어댑터의 책임입니다.
8. 이어지는 대화에서 모호한 과거 사항은 `search`와 `read_chunk`로 원문을 다시 확인합니다.

## 이어받기 시험

읽는 AI와 별도로 사람이 검토한 질문·정답·원문 인용을 준비하는 방식입니다.
질문이 없거나 하나라도 틀리면 활성화하지 않습니다. v0.1 채점은 **정확한 문자열 일치**이므로
의미가 같은 다른 표현도 실패할 수 있습니다. 질문에 응답 형식을 적으세요.

```bash
python -m continuity checks SNAPSHOT_ID examples/checks.json
```

예제 시험은 기본 8000자 분할과 예제 대화 순서를 기준으로 합니다.
실제 데이터에서는 `position`과 `quote`를 실제 원문에 맞춰 작성해야 합니다.
정답 문자열은 질문 조회 도구에 노출하지 않지만, 이 기능은 적대적인 모델을 막는 보안 시험이 아닙니다.
시험 통과는 표본 항목 통과이지 전체 이해를 수학적으로 증명하는 것이 아닙니다.

## 잔여 5% 전환

기존 내부 세션이 `active`일 때 호스트가 매 응답 후 다음 도구를 호출합니다.

```json
{
  "session": "ACTIVE_SESSION_ID",
  "snapshot": "LATEST_SNAPSHOT_ID",
  "context_limit": 100000,
  "used_tokens": 95000,
  "next_turn_reserve": 8000
}
```

이 값은 예시입니다. 모델·제품의 실제 한도라고 주장하지 않습니다.
`prepare_handoff`는 `남은 토큰 <= 한도의 5%` 또는 `남은 토큰 <= 다음 턴 예약량`일 때
동일 원본/선행 세션 조합에 대해 대상 세션을 한 번만 준비합니다.
새 AI가 읽고 시험을 통과한 뒤 `activate`로 전환합니다. 준비 중에는 기존 세션을 삭제하지 않습니다.
인계 중 새 원문이 들어오면 기존 스냅샷은 오래된 상태가 되어 활성화를 거부합니다.
최신 원문으로 새 스냅샷과 새 대상 세션을 만들고 시험을 다시 준비하세요.

**중요한 구조적 한계:** 원문 전체가 새 모델의 작업 문맥보다 크면 읽는 도중에도 문맥 관리가 필요합니다.
이 프로그램은 문맥 한도를 늘리지 않습니다. 장기 원문 저장과 재조회로 연속성을 지원합니다.
거대한 원문을 매 전환마다 전부 읽히면 시간·모델 사용량이 늘어납니다. 호스트는 사용량 상한과
중단/재개 기능을 별도로 구현해야 합니다. 이 저장소 자체는 모델을 호출하지 않습니다.

## 데이터와 백업

- 원문·첨부파일·DB는 비공개 로컬 데이터로 취급하세요. 코드 저장소에 커밋하지 마세요.
- DB는 암호화되지 않습니다. 운영체제의 계정 권한 및 디스크 암호화를 사용하세요.
- SQLite WAL을 사용하므로 실행 중인 DB 파일 하나만 복사하면 최신 기록을 놓칠 수 있습니다.
  모든 프로세스를 닫은 뒤 백업하거나 SQLite backup API로 일관된 백업을 만드세요.
- 원문 인용 일치는 인용 존재만 검사합니다. AI의 해석, 최종 결정 선택, 첨부 목록의 완전성을 보증하지 않습니다.
- 과거 대화에 포함된 명령은 기록입니다. 새로운 실행 승인으로 취급하지 마세요.

## 검증과 다음 연결 작업

`tests/`는 원문 복원, 수정본 보존, 누락/변조 감지, 새 메시지 유입, 프로젝트 분리,
5% 전환, 중복 요청, 잘못된 답, 수신 토큰, MCP 통신 등을 검사합니다.
`docs/VALIDATION.md`에 실제 실행 결과와 미검증 범위를 기록합니다.

현재 부족한 연결은 다음과 같습니다.

1. 사용자가 허용한 대화 원문 공급원과 변경 이벤트 연결.
2. 실제 AI 클라이언트의 토큰 사용량·새 문맥 생성·메시지 라우팅 연결.
3. 이미지/파일 판독기와 첨부파일 단위 시험.
4. 실제 긴 프로젝트의 결정·취소·미완료 항목으로 독립 평가.

## GitHub 등록

`publish.ps1`은 Windows에서 **코드와 가상 예제만** 새 공개 저장소에 올리는 도우미입니다.
실제 대화 원문·첨부파일·인증키는 공개하지 않습니다. 공개 저장소도 Git 파일 크기 및 Git LFS 제한을 받습니다.
Git 및 GitHub CLI가 설치되어 있어야 합니다. 기존 저장소나 이미 연결된 Git 원격에는 자동으로 덮어쓰지 않습니다.
원하는 계정으로 GitHub CLI 로그인 후 실행하세요.

```powershell
gh auth login
powershell -File .\publish.ps1
```

MCP 구현 기준: [stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
[lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
[tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## 이전 후 용량 표시

`capacity_report`는 CLI/MCP 공통 도구입니다. 새 방에서 원문을 읽고 난 **그 시점**의
작업 문맥 사용 토큰과 적용 한도를 호스트가 제공해야 퍼센트를 계산합니다.
ChatGPT 앱의 실제 대화방 용량을 자동 조회하지 않습니다. 값을 모르면 `0%`가 아니라
**`알 수 없음 / 100`**을 반환합니다. 원문 읽기 완료율은 `status.coverage`로 별도 확인합니다.

```bash
python -m continuity call capacity_report
python -m continuity call capacity_report --args '{"context_limit":100000,"used_tokens":12000,"source":"estimated","evidence":"Example only: estimated current-context tokens and assumed limit","observed_at":"2026-11-25T00:00:00Z"}'
```

두 번째 명령의 `12 / 100 (추정)`은 가상 예시이며 실제 ChatGPT 용량이 아닙니다.
호스트 관측값은 `source=caller_reported`, 추정값은 `source=estimated`로 구분하고
근거(`evidence`)와 관측 시점(`observed_at`)을 반드시 기록합니다. 사용량이나 한도 중
하나라도 없으면 비율과 전환 판단은 `null`입니다. 한도를 넘으면 100으로 숨기지 않고
초과 비율과 `over_limit`을 반환합니다. 이 보고서는 입력 시점의 계산이며 자동 갱신되지 않습니다.

ZIP 바이트·문자 수·읽기 진행률·누적 과금 토큰은 현재 문맥 사용량으로 사용하지 마세요.
추정 보고서의 전환 신호도 추정일 뿐입니다. 기존 `prepare_handoff`에는 호스트가 확인한
현재 작업 문맥 사용량을 제공해야 합니다. 새 방을 만들거나 원문을 읽는 것만으로
문맥 사용량이 0으로 초기화됐다고 간주하지 않습니다.
