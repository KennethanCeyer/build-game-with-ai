# Agent Playtest Lab

Google ADK, A2A, Gemini, 그리고 간단한 3D 게임 런타임을 연결해 보는 1시간 핸즈온용 데모입니다.

이 프로젝트의 목표는 "에이전트가 게임에서 쓸모 있을 수 있다"를 초급자도 직접 볼 수 있게 만드는 것입니다. 그래서 기능을 많이 넣기보다 세 가지 장면만 남겼습니다.

- NPC 퀘스트: NPC 대화와 화면 단서, 넓은 상태만 보고 입력 버퍼로 퀘스트 진행을 시도합니다.
- 미로: 에이전트가 화면과 상태를 보고 `WASD`, `Shift`, `E` 입력만으로 이동을 시도합니다.
- 기억 퍼즐: 플레이 버튼을 누르면 5색 패드가 점멸하고, 에이전트가 같은 순서를 입력으로 반복합니다.

전체 QA smoke test처럼 설명량이 큰 기능은 초급자 실습 흐름을 흐려서 제거했습니다.

## 학습 목표

- ADK `LlmAgent`가 실제 Gemini 모델을 호출하는 흐름을 본다.
- 에이전트가 게임 상태를 직접 조작하지 않고 사용자와 같은 입력 버퍼만 쓰도록 설계한다.
- 브라우저 캔버스 캡처가 Gemini 입력 이미지로 전달되는 것을 확인한다.
- 모델 호출, tool call, tool response가 콘솔 trace로 어떻게 보이는지 이해한다.
- 게임 코드와 에이전트 코드의 관심사를 분리한다.

## 설치 방법

Python 의존성을 설치합니다.

```bash
pip install -r requirements.txt
```

워크스페이스 루트의 `.env`에 Gemini API 키를 둡니다.

```env
GOOGLE_API_KEY=...
```

실행합니다.

```bash
python run_demo.py
```

브라우저에서 엽니다.

```text
http://127.0.0.1:8787
```

## 조작법

```text
WASD          이동
Shift + WASD  달리기
Space         점프
E             상호작용
마우스 드래그   3인칭 카메라 회전
마우스 휠       줌
`              에이전트 콘솔 열기
```

## 에이전트 소개

브라우저 콘솔에서 `/help`를 입력하면 즉시 도움말을 봅니다. `/help`를 제외한 자연어 요청은 실제 ADK agent의 user message로 들어갑니다.

에이전트에게 제공되는 핵심 도구는 두 개입니다.

```text
inspect_game_state
apply_input_buffer
```

`inspect_game_state`는 현재 게임 상태를 읽습니다.
단, ADK에 반환되는 state는 브라우저 렌더링용 전체 state가 아닙니다. 좌표, obstacle 목록, zone center/radius, 퍼즐 정답 payload, 퀘스트 아이템 flag는 제거하고, 화면/이벤트 로그/HUD로 플레이어가 알 수 있는 수준의 요약만 반환합니다.

`apply_input_buffer`는 다음 같은 사용자 입력 프레임만 실행합니다.

```json
{"keys": ["ShiftLeft", "KeyW"], "duration_ms": 240}
```

좌표 순간이동, 플래그 직접 수정, 정답 처리 함수는 agent tool로 제공하지 않습니다.
NPC 퀘스트도 예외가 아닙니다. Agent는 대화 박스, 캔버스 이미지, 최근 이벤트, 넓은 flags만 보고 다음 `WASD`/`E` 입력을 고릅니다.

## 문제 상황

게임 QA와 디버깅에서 반복 작업이 많습니다.

- 캐릭터가 특정 지점까지 갈 수 있는지 확인한다.
- NPC 대화나 상호작용 순서를 반복한다.
- 화면 단서와 상호작용 결과가 의도대로 이어지는지 캡처로 확인한다.
- 실패했을 때 어떤 입력과 상태 변화가 있었는지 남긴다.

사람이 매번 직접 확인하면 오래 걸리고, 순수 하드코딩 테스트만으로는 화면 단서 기반 문제를 다루기 어렵습니다.

## 해결 방식

이 데모는 에이전트를 "게임 내부 치트 함수 호출자"가 아니라 "입력 버퍼를 고르는 플레이어"로 둡니다.

흐름은 다음과 같습니다.

```text
브라우저
  현재 WebGL 캔버스를 PNG로 캡처
  자연어 요청과 함께 서버로 전송

FastAPI
  ADK LlmAgent 실행
  Gemini에 텍스트 + 이미지 전달
  tool call을 NDJSON stream으로 브라우저에 전달

게임 런타임
  inspect_game_state로 상태 제공
  apply_input_buffer로 WASD/Shift/Space/E 입력만 처리

브라우저 콘솔
  Agent input image 표시
  model_start, tool_call, input replay, tool_response 표시
  각 콘솔 박스에 실제 사용 모델 배지 표시
  입력 프레임을 화면에서 실시간 재생
```

## 실습 가이드

### 1. 직접 움직여 보기

먼저 사람이 직접 `WASD`, `Shift`, `E`로 조작합니다.

NPC에게 말을 걸면 화면 아래 대화 박스가 뜹니다. 미로에는 시작점과 끝점이 있고, 벽 충돌이 걸려 있습니다. 퍼즐은 플레이 버튼을 눌러 점멸 순서를 본 뒤 같은 순서로 5색 패드를 눌러야 합니다.
플레이어와 NPC는 서로 다른 3D 캐릭터 에셋을 사용합니다. NPC는 색만 바꾼 복제 모델이 아니라 idle/walk/run 애니메이션이 포함된 별도 GLB 모델을 각각 로드합니다.

### 2. 콘솔에서 이미지 입력 확인하기

`` ` `` 키로 에이전트 콘솔을 열고 다음을 입력합니다.

```text
현재 화면과 상태를 보고 다음에 무엇을 할 수 있는지 짧게 설명해줘
```

콘솔에 `Agent input image`가 표시됩니다. 이것이 Gemini에 전달된 캔버스 캡처입니다.

### 3. NPC 퀘스트 실습

```text
NPC 퀘스트를 대화와 화면 단서만 보고 입력 버퍼로 완료해봐
```

콘솔에서 확인할 것:

- 퀘스트 해법이 프롬프트가 아니라 NPC 대화 이벤트에서 드러나는지
- Agent가 `apply_input_buffer`로만 이동하고 `E` 상호작용을 보내는지
- 대화 박스와 최근 이벤트가 다음 행동 근거로 쓰이는지
- 최종 state에서 `quest_complete`가 켜졌는지

### 4. 미로 실습

```text
미로를 입력만으로 탈출해봐
```

콘솔에서 확인할 것:

- 어떤 Gemini 모델이 호출됐는지
- `inspect_game_state`가 언제 호출됐는지
- `apply_input_buffer`가 어떤 키 프레임을 보냈는지
- 캐릭터가 화면에서 실제로 이동하는지
- 최종 state에서 `maze_escaped`가 켜졌는지

### 5. 퍼즐 실습

```text
퍼즐을 화면 단서 기반으로 풀고 호출 그래프를 보여줘
```

퍼즐은 한 번에 정답 플래그를 켜지 않습니다. 플레이 버튼, 5색 패드 입력, 오답 reset이 모두 게임 규칙으로 처리됩니다.

## 점진적 개선 순서

핸즈온에서는 기능을 한 번에 다 설명하지 말고 다음 순서로 주석을 해제하며 진행합니다.

에이전트 배선만 연습할 때는 완성본과 starter를 나란히 봅니다.

```text
solution/agentic_game_demo/agent_setup.py  완성본
starter/agentic_game_demo/agent_setup.py   참가자용 빈칸
```

참가자가 직접 수정해야 하는 핵심은 `LoopAgent`, `LlmAgent`, `McpToolset`, `exit_loop` 연결뿐입니다. 게임 런타임, 충돌, UI, 캡처, MCP 서버 내부 구현은 실습 중에 건드리지 않습니다.

1. `inspect_game_state`만 연결한다.
2. `apply_input_buffer`를 연결한다.
3. 콘솔 NDJSON stream을 켠다.
4. 캔버스 캡처 이미지를 Gemini 입력으로 붙인다.
5. NPC 대화와 퀘스트 진행을 시도한다.
6. 미로 탈출을 시도한다.
7. 기억 퍼즐을 시도한다.

## 추가로 붙여볼 소재

- 실패한 입력 프레임을 저장하고 재생하는 replay viewer
- NPC 대화 로그를 LiveOps QA 리포트로 내보내기
- 미로 생성 seed를 바꿔 regression set 만들기
- Playwright screenshot과 ADK trace를 묶은 QA 리포트
- A2A로 퀘스트 검증 agent와 플레이 조작 agent를 분리하는 심화 실습

## 완료 및 결론

이 데모에서 중요한 메시지는 하나입니다.

에이전트가 게임 개발에서 의미 있으려면 내부 값을 몰래 바꾸면 안 됩니다. 화면을 보고, 상태를 읽고, 사용자와 같은 입력을 보내고, 결과를 다시 관찰해야 합니다.

그 구조가 갖춰지면 에이전트는 반복 QA, NPC 퀘스트 검증, 퍼즐/튜토리얼 검증, 디버그 재현에 실제로 쓸 수 있습니다.
