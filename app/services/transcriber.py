"""
WhisperX 변환 서비스 — 역할 C 핵심 모듈

파이프라인:
  1. ffmpeg 전처리 (16kHz mono WAV)
  2. whisperX STT (음성 → 텍스트)
  3. whisperX align (단어 단위 타임스탬프)
  4. whisperX diarize (화자 분리) — 설정으로 on/off 가능
  5. 결과를 documents 테이블에 저장 + meetings 에 연결
"""

import json
import logging
import re
from typing import Any

import whisperx

from app.services.audio_preprocessor import preprocess_audio, cleanup_processed_file

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 유틸리티 함수
# ──────────────────────────────────────────────
def _fmt_time(seconds: float) -> str:
    """초(float)를 HH:MM:SS 형식 문자열로 변환."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def strip_timestamps(content: str) -> str:
    """
    타임스탬프를 제거하고 화자 태그 + 텍스트만 반환.

    변환 전: [00:00:05 - 00:00:12] [Speaker 1] 안녕하세요
    변환 후: [Speaker 1] 안녕하세요

    D역할(요약/RAG)에 텍스트를 넘길 때 사용.
    """
    return re.sub(r'\[\d{2}:\d{2}:\d{2}\s*-\s*\d{2}:\d{2}:\d{2}\]\s*', '', content)

# ──────────────────────────────────────────────
# 모델 캐싱 (앱 수명 동안 한 번만 로드)
# ──────────────────────────────────────────────
_whisper_model = None
_align_model = None
_align_metadata = None
_diarize_pipeline = None


def _get_whisper_model(model_size: str, device: str):
    global _whisper_model
    if _whisper_model is None:
        compute_type = "float16" if device == "cuda" else "int8"
        _whisper_model = whisperx.load_model(
            model_size, device=device, compute_type=compute_type
        )
        logger.info(f"WhisperX 모델 로드 완료: {model_size} / {device}")
    return _whisper_model


def _get_align_model(language_code: str, device: str):
    global _align_model, _align_metadata
    if _align_model is None:
        _align_model, _align_metadata = whisperx.load_align_model(
            language_code=language_code, device=device
        )
        logger.info(f"Align 모델 로드 완료: {language_code}")
    return _align_model, _align_metadata


def _get_diarize_pipeline(hf_token: str, device: str):
    global _diarize_pipeline
    if _diarize_pipeline is None:
        _diarize_pipeline = whisperx.DiarizationPipeline(
            use_auth_token=hf_token, device=device
        )
        logger.info("화자 분리 파이프라인 로드 완료")
    return _diarize_pipeline


# ──────────────────────────────────────────────
# 잡 상태 관리 (메모리 기반)
# - status 컬럼이 DB에 없으므로 dict 로 관리
# - 서버 재시작 시 초기화됨 (5일 프로젝트에선 충분)
# ──────────────────────────────────────────────
job_status: dict[int, dict[str, str]] = {}
# { meeting_id: {"status": "transcribing", "message": "음성 변환 중..."} }


def get_job_status(meeting_id: int) -> dict[str, str]:
    """현재 잡 상태 조회"""
    return job_status.get(meeting_id, {"status": "unknown", "message": ""})


def _update_status(meeting_id: int, status: str, message: str = ""):
    job_status[meeting_id] = {"status": status, "message": message}
    logger.info(f"[Meeting {meeting_id}] {status}: {message}")


# ──────────────────────────────────────────────
# 메인 변환 함수 (BackgroundTasks 에서 호출)
# ──────────────────────────────────────────────
def run_transcription(
    meeting_id: int,
    audio_path: str,
    owner_id: int,
    meeting_title: str,
    # 설정값 (config 에서 주입)
    model_size: str = "medium",
    device: str = "cuda",
    hf_token: str = "",
    enable_diarization: bool = True,
):
    """
    백그라운드에서 실행되는 전체 변환 파이프라인.

    완료 후:
      - documents 테이블에 transcript INSERT
      - meetings.transcript_document_id UPDATE
      - job_status 를 "completed" 로 갱신

    Args:
        meeting_id: meetings.id
        audio_path: 업로드된 오디오 파일 경로
        owner_id: 회의 소유자 user id
        meeting_title: 회의 제목 (document 제목 생성용)
        model_size: whisper 모델 크기
        device: cuda / cpu
        hf_token: HuggingFace 토큰 (화자 분리용)
        enable_diarization: 화자 분리 사용 여부
    """
    # DB 세션은 함수 내에서 생성 (백그라운드 스레드이므로)
    from app.database import SessionLocal
    from app.models import Document, SourceType  # 기존 Document 모델 사용

    db = SessionLocal()

    try:
        # ── 1단계: 전처리 ──
        _update_status(meeting_id, "processing", "오디오 전처리 중...")
        processed_path = preprocess_audio(audio_path)

        # ── 2단계: STT ──
        _update_status(meeting_id, "transcribing", "음성을 텍스트로 변환 중...")
        model = _get_whisper_model(model_size, device)
        audio = whisperx.load_audio(processed_path)
        result = model.transcribe(audio, language="ko")

        # ── 3단계: 단어 단위 정렬 ──
        _update_status(meeting_id, "transcribing", "타임스탬프 정렬 중...")
        align_model, metadata = _get_align_model("ko", device)
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device=device
        )

        # ── 4단계: 화자 분리 (선택) ──
        if enable_diarization and hf_token:
            _update_status(meeting_id, "diarizing", "화자 분리 중...")
            try:
                diarize_model = _get_diarize_pipeline(hf_token, device)
                diarize_segments = diarize_model(audio)
                result = whisperx.assign_word_speakers(diarize_segments, result)
            except Exception as e:
                logger.warning(f"화자 분리 실패 (STT 결과는 유지): {e}")
                # 화자 분리 실패해도 STT 결과는 유지

        # ── 5단계: 결과 정리 ──
        segments = result.get("segments", [])
        transcript_segments = []
        full_text_lines = []

        for seg in segments:
            speaker = seg.get("speaker", None)
            text = seg.get("text", "").strip()
            start = round(seg.get("start", 0), 1)
            end = round(seg.get("end", 0), 1)

            transcript_segments.append({
                "start": start,
                "end": end,
                "speaker": speaker,
                "text": text,
            })

            # full_text 생성: [타임스탬프] [화자] 텍스트
            # DB에는 타임스탬프 포함 전체 저장, D에 넘길 때는 strip_timestamps()로 제거
            ts = f"[{_fmt_time(start)} - {_fmt_time(end)}]"
            if speaker:
                full_text_lines.append(f"{ts} [{speaker}] {text}")
            else:
                full_text_lines.append(f"{ts} {text}")

        full_text = "\n".join(full_text_lines)

        # ── 6단계: DB 저장 ──
        _update_status(meeting_id, "saving", "결과 저장 중...")

        # documents 테이블에 INSERT
        doc = Document(
            owner_id=owner_id,
            title=f"{meeting_title} - 회의록",
            content=full_text,
            source_type=SourceType.meeting_transcript,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # meetings.transcript_document_id UPDATE
        from app.models_meeting import Meeting

        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if meeting:
            meeting.transcript_document_id = doc.id
            db.commit()

        # 세그먼트 상세 정보는 잡 상태에 보관 (프론트에서 조회용)
        job_status[meeting_id] = {
            "status": "completed",
            "message": "변환 완료",
            "document_id": doc.id,
            "segments": transcript_segments,
            "full_text": full_text,
        }
        logger.info(f"[Meeting {meeting_id}] 변환 완료 → document.id={doc.id}")

    except Exception as e:
        _update_status(meeting_id, "failed", f"변환 실패: {str(e)}")
        logger.error(f"[Meeting {meeting_id}] 변환 실패: {e}", exc_info=True)

    finally:
        db.close()
        # 전처리 임시 파일 정리
        cleanup_processed_file(audio_path)
