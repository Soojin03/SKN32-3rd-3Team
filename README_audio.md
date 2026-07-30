# 역할 C — 음성 파이프라인 (STT + 화자분리)

## 1. 프로젝트 개요

회의록 자동화 프로젝트의 **음성 처리 파트**입니다.
회의/통화 녹음 파일을 업로드하면 자동으로 텍스트 변환(STT) + 화자 분리(Speaker Diarization)를 수행하고,
결과를 DB에 저장하여 D역할(LLM 요약·RAG)이 활용할 수 있도록 합니다.

### 전체 시스템에서의 위치

```
사용자 → [B: 프론트엔드] → [C: 음성 파이프라인] → [A: DB/인증] → [D: LLM·RAG]
             │                    │                                    │
         파일 업로드         STT + 화자분리                     요약 + 벡터DB + 챗봇
             │                    │                                    │
             └── 폴링으로 ────── 잡 상태 조회 ────────────────────────────┘
                 진행률 표시
```

### 기술 스택

| 구분 | 기술 |
|---|---|
| STT 엔진 | WhisperX (faster-whisper 기반) |
| 화자 분리 | pyannote (WhisperX 내장) |
| 오디오 전처리 | ffmpeg (16kHz mono WAV 변환) |
| Whisper 모델 | medium (한국어 최적 성능/속도 균형) |
| GPU | RunPod RTX 3090 (또는 CUDA 지원 GPU) |
| 프레임워크 | FastAPI (BackgroundTasks로 비동기 처리) |
| DB | MySQL + SQLAlchemy (A역할 기존 구조 활용) |

---

## 2. 파일 구조

```
app/
├── core/
│   └── config_audio.py          # Settings 필드 추가 가이드
├── models_meeting.py            # Meeting ORM 모델
├── schemas_audio.py             # Pydantic 요청/응답 스키마
├── routers/
│   └── audio.py                 # 오디오 API 엔드포인트 (4개)
├── services/
│   ├── transcriber.py           # WhisperX 파이프라인 핵심 로직
│   └── audio_preprocessor.py    # ffmpeg 전처리 + 파일 검증
├── main_patch.py                # main.py 패치 참고용
.env.example                     # 환경변수 템플릿
.gitignore                       # Git 제외 설정
requirements_audio.txt           # 추가 패키지 목록
```

---

## 3. 처리 파이프라인

오디오 업로드부터 DB 저장까지 6단계로 동작합니다.

```
[1] 오디오 업로드
 │  POST /api/audio/upload (파일 검증 → uploads/ 저장 → meetings INSERT)
 ▼
[2] ffmpeg 전처리
 │  원본 → 16kHz mono WAV 변환 (Whisper 최적 입력)
 ▼
[3] WhisperX STT
 │  음성 → 텍스트 변환 (medium 모델, 한국어)
 ▼
[4] 타임스탬프 정렬
 │  단어 단위 시간 정보 매칭
 ▼
[5] 화자 분리 (선택)
 │  pyannote로 Speaker 1, 2, ... 태깅
 ▼
[6] DB 저장
    documents INSERT (source_type='meeting_transcript')
    meetings UPDATE (transcript_document_id 연결)
```

각 단계에서 잡 상태가 메모리 dict에 기록되며, 프론트엔드가 `/status` API를 폴링하여 진행률을 표시합니다.

### 잡 상태 값

| status | 설명 |
|---|---|
| `uploaded` | 업로드 완료, 변환 대기 |
| `processing` | ffmpeg 전처리 중 |
| `transcribing` | WhisperX STT / 타임스탬프 정렬 중 |
| `diarizing` | 화자 분리 중 |
| `saving` | DB 저장 중 |
| `completed` | 변환 완료 |
| `failed` | 변환 실패 (에러 메시지 포함) |

---

## 4. Transcript 저장 형식

### DB 저장 형식 (documents.content)

타임스탬프 + 화자 태그 포함 전체 텍스트:

```
[00:00:05 - 00:00:12] [Speaker 1] 안녕하세요 오늘 회의 시작하겠습니다.
[00:00:13 - 00:00:18] [Speaker 2] 네 지난주 이슈부터 보시죠.
[00:01:05 - 00:01:15] [Speaker 1] 신규 기능 일정은 다음 주 목요일까지입니다.
```

### D역할에 넘기는 형식 (타임스탬프 제거)

`strip_timestamps()` 유틸로 타임스탬프만 제거:

```python
from app.services.transcriber import strip_timestamps

clean_text = strip_timestamps(document.content)
# 결과:
# [Speaker 1] 안녕하세요 오늘 회의 시작하겠습니다.
# [Speaker 2] 네 지난주 이슈부터 보시죠.
# [Speaker 1] 신규 기능 일정은 다음 주 목요일까지입니다.
```

이렇게 하면 DB에는 원본(타임스탬프 포함)이 보존되고, D는 LLM 요약/RAG에 최적화된 텍스트를 받습니다.

---

## 5. API 명세

### 5-1. POST /api/audio/upload

오디오 파일 업로드 + 백그라운드 변환 시작.

```bash
curl -X POST http://localhost:8000/api/audio/upload \
  -F "file=@meeting.mp3" \
  -F "title=7월 정기 회의"
```

응답:
```json
{
  "meeting_id": 1,
  "status": "uploaded",
  "message": "변환이 시작되었습니다. /api/audio/status/{meeting_id} 로 진행 상태를 확인하세요."
}
```

### 5-2. GET /api/audio/status/{meeting_id}

변환 진행 상태 조회. 프론트에서 2~3초 간격 폴링 권장.

```bash
curl http://localhost:8000/api/audio/status/1
```

응답:
```json
{
  "meeting_id": 1,
  "status": "transcribing",
  "progress_message": "음성을 텍스트로 변환 중..."
}
```

### 5-3. GET /api/audio/result/{meeting_id}

변환 완료된 결과 조회. status가 `completed`가 아니면 202 반환.

```bash
curl http://localhost:8000/api/audio/result/1
```

응답:
```json
{
  "meeting_id": 1,
  "status": "completed",
  "document_id": 5,
  "segments": [
    {
      "start": 5.2,
      "end": 12.8,
      "speaker": "Speaker 1",
      "text": "안녕하세요 오늘 회의 시작하겠습니다."
    }
  ],
  "full_text": "[00:00:05 - 00:00:12] [Speaker 1] 안녕하세요 오늘 회의 시작하겠습니다.\n..."
}
```

### 5-4. GET /api/audio/list

전체 회의 목록 + 각 회의의 변환 상태 조회.

```bash
curl http://localhost:8000/api/audio/list
```

응답:
```json
[
  {
    "meeting_id": 1,
    "title": "7월 정기 회의",
    "status": "completed",
    "transcript_document_id": 5,
    "summary_document_id": null,
    "created_at": "2026-07-30T14:30:00"
  }
]
```

---

## 6. 실행 방법

### 6-1. 사전 요구사항

| 항목 | 설명 |
|---|---|
| Python | 3.10 이상 |
| CUDA | GPU 사용 시 CUDA 11.8+ 및 cuDNN 필요 |
| ffmpeg | 시스템에 설치 필요 |
| HuggingFace 토큰 | 화자 분리 사용 시 필수 |

### 6-2. ffmpeg 설치

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

**Windows 수동 설치:**

1. https://www.gyan.dev/ffmpeg/builds/ 접속
2. release builds 섹션에서 `ffmpeg-release-essentials.7z` (32MB) 다운로드
3. Bandizip 등으로 압축 해제
4. 압축 해제된 폴더 안의 `bin` 경로 복사 (예: `C:\Users\{사용자}\Downloads\ffmpeg-x.x.x-essentials_build\bin`)
5. 시스템 PATH에 등록:
   - `Win + R` → `sysdm.cpl` → 고급 → 환경 변수
   - 시스템 변수에서 `Path` 선택 → 편집 → 새로 만들기 → bin 경로 붙여넣기 → 확인
6. VS Code / 터미널 재시작 후 확인:

```bash
ffmpeg -version
```

### 6-3. Python 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 기존 패키지 + 오디오 패키지 설치
pip install -r requirements.txt
pip install -r requirements_audio.txt

# GPU 사용 시 PyTorch CUDA 버전 확인
python -c "import torch; print(torch.cuda.is_available())"
```

### 6-4. 환경변수 설정

```bash
# .env.example을 복사하여 .env 생성
cp .env.example .env

# .env 파일 편집 — 아래 항목을 실제 값으로 수정
```

필수 환경변수:

| 변수 | 설명 | 기본값 |
|---|---|---|
| `HF_TOKEN` | HuggingFace 토큰 (화자분리용) | 없음 (필수) |
| `WHISPER_MODEL` | Whisper 모델 크기 | `medium` |
| `WHISPER_DEVICE` | 실행 디바이스 | `cuda` |
| `ENABLE_DIARIZATION` | 화자 분리 on/off | `true` |
| `UPLOAD_DIR` | 업로드 파일 저장 경로 | `uploads` |
| `MAX_AUDIO_SIZE_MB` | 최대 업로드 크기 (MB) | `100` |
| `ALLOWED_AUDIO_EXTENSIONS` | 허용 확장자 | `.mp3,.wav,.m4a,.webm,.ogg,.flac` |

### 6-5. HuggingFace 라이선스 동의

화자 분리를 사용하려면 아래 두 모델에 대해 **HuggingFace에서 라이선스 동의**가 필요합니다 (무료):

1. https://huggingface.co/pyannote/speaker-diarization-3.1 → "Agree and access repository" 클릭
2. https://huggingface.co/pyannote/segmentation-3.0 → "Agree and access repository" 클릭

토큰은 https://huggingface.co/settings/tokens 에서 발급받아 `.env`의 `HF_TOKEN`에 입력합니다.

### 6-6. 서버 실행

```bash
# 개발 모드 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# RunPod 등 GPU 서버에서 실행
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> workers는 1로 유지하세요. WhisperX 모델이 GPU 메모리에 캐싱되므로 멀티 워커 시 VRAM 부족 가능.

### 6-7. 빠른 테스트 (화자 분리 없이)

HF 토큰 없이 STT만 테스트하려면:

```bash
# .env에서
ENABLE_DIARIZATION=false
WHISPER_DEVICE=cpu     # GPU 없는 경우
```

```bash
# 업로드 테스트
curl -X POST http://localhost:8000/api/audio/upload \
  -F "file=@test_audio.mp3" \
  -F "title=테스트 회의"

# 상태 확인 (2~3초 간격으로 반복)
curl http://localhost:8000/api/audio/status/1

# 결과 조회
curl http://localhost:8000/api/audio/result/1
```

---

## 7. 기존 프로젝트 병합 가이드

### 7-1. Base 통일 (필수)

`models_meeting.py` 상단에서 기존 `database.py`의 Base를 사용하도록 변경:

```python
# 변경 전 (독립 실행용)
from sqlalchemy.orm import declarative_base
Base = declarative_base()

# 변경 후 (병합)
from app.database import Base
```

### 7-2. Settings 필드 추가

`app/core/config.py`의 Settings 클래스에 `config_audio.py`의 필드를 추가:

```python
class Settings(BaseSettings):
    # ... 기존 MySQL, JWT 설정 ...

    # ── Audio / WhisperX (C 담당) ──
    UPLOAD_DIR: str = "uploads"
    WHISPER_MODEL: str = "medium"
    WHISPER_DEVICE: str = "cuda"
    HF_TOKEN: str = ""
    ENABLE_DIARIZATION: bool = True
    MAX_AUDIO_SIZE_MB: int = 100
    ALLOWED_AUDIO_EXTENSIONS: str = ".mp3,.wav,.m4a,.webm,.ogg,.flac"
```

### 7-3. main.py 라우터 등록

```python
from app.routers import audio

app.include_router(audio.router)
```

### 7-4. 로그인 연동

`routers/audio.py`의 `owner_id=1` 하드코딩을 실제 JWT 인증 유저로 교체:

```python
# 변경 전
meeting = Meeting(owner_id=1, ...)

# 변경 후 (A의 인증 미들웨어 사용)
from app.core.security import get_current_user

@router.post("/upload")
async def upload_audio(
    ...,
    current_user: User = Depends(get_current_user),
):
    meeting = Meeting(owner_id=current_user.id, ...)
```

---

## 8. D역할(LLM·RAG) 연결 포인트

C가 저장한 데이터를 D가 사용하는 흐름:

```
documents 테이블
  └─ source_type = "meeting_transcript"
  └─ content = "[00:00:05 - 00:00:12] [Speaker 1] 발화..." (타임스탬프 포함)
       │
       ├─ strip_timestamps() 적용
       │     └─ "[Speaker 1] 발화..." (화자 태그만)
       │
       ├─→ D: LLM 요약 생성 → documents에 source_type="meeting_summary"로 저장
       │     → meetings.summary_document_id 업데이트
       │
       └─→ D: 청킹 → 임베딩 → 벡터DB → RAG 챗봇 검색 대상
```

### D가 사용할 코드 예시

```python
from app.services.transcriber import strip_timestamps

# DB에서 transcript 문서 조회
doc = db.query(Document).filter(Document.id == meeting.transcript_document_id).first()

# 타임스탬프 제거 후 LLM/RAG에 전달
clean_text = strip_timestamps(doc.content)
```

---

## 9. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `CUDA out of memory` | GPU VRAM 부족 | `WHISPER_MODEL=small`로 변경 또는 workers=1 확인 |
| `ffmpeg: command not found` | ffmpeg 미설치 | 6-2 참고하여 설치 |
| `pyannote 401 Unauthorized` | HF 토큰 문제 | 토큰 재발급 + 라이선스 동의 확인 (6-5) |
| 화자 분리 실패, STT는 정상 | pyannote 모델 접근 불가 | HF 라이선스 동의 확인, 로그에 warning 출력됨 |
| `validate_audio_file` 거부 | 확장자/크기 제한 | `.env`의 `ALLOWED_AUDIO_EXTENSIONS`, `MAX_AUDIO_SIZE_MB` 조정 |
| CPU에서 너무 느림 | GPU 미사용 | `WHISPER_DEVICE=cuda` + CUDA 설치 확인 |
