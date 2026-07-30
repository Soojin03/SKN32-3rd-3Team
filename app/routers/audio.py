"""
Audio 라우터 — 역할 C 담당
엔드포인트:
  POST /api/audio/upload     — 오디오 업로드 + 백그라운드 변환 시작
  GET  /api/audio/status/{id} — 잡 진행 상태 조회 (프론트 폴링용)
  GET  /api/audio/result/{id} — 변환 결과 조회 (세그먼트 + 전체 텍스트)
"""

import os
import shutil
import uuid

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException

from app.core.config import get_settings
from app.services.audio_preprocessor import validate_audio_file
from app.services.transcriber import run_transcription, get_job_status, job_status

router = APIRouter(prefix="/api/audio", tags=["Audio"])

settings = get_settings()


@router.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    title: str = Form(default="제목 없는 회의"),
    background_tasks: BackgroundTasks = None,
):
    """
    오디오 파일을 업로드하고 백그라운드 변환을 시작합니다.

    - 파일 검증 (확장자, 크기)
    - uploads/ 에 저장
    - meetings 테이블에 레코드 생성
    - 백그라운드에서 whisperX 변환 시작

    Returns:
        meeting_id, status
    """
    # ── 1) 파일 검증 ──
    # file.size 가 None 일 수 있으므로, 읽어서 확인
    contents = await file.read()
    file_size = len(contents)

    error = validate_audio_file(
        filename=file.filename,
        file_size=file_size,
        allowed_extensions=settings.ALLOWED_AUDIO_EXTENSIONS,
        max_size_mb=settings.MAX_AUDIO_SIZE_MB,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    # ── 2) 파일 저장 ──
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(contents)

    # ── 3) meetings 레코드 생성 ──
    from app.database import SessionLocal
    from app.models_meeting import Meeting

    db = SessionLocal()
    try:
        meeting = Meeting(
            owner_id=1,  # TODO: 로그인 연동 후 실제 유저 ID 로 교체
            title=title,
            audio_path=filepath,
        )
        db.add(meeting)
        db.commit()
        db.refresh(meeting)
        meeting_id = meeting.id
        owner_id = meeting.owner_id
    finally:
        db.close()

    # ── 4) 잡 상태 초기화 + 백그라운드 변환 시작 ──
    job_status[meeting_id] = {"status": "uploaded", "message": "업로드 완료"}

    background_tasks.add_task(
        run_transcription,
        meeting_id=meeting_id,
        audio_path=filepath,
        owner_id=owner_id,
        meeting_title=title,
        model_size=settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        hf_token=settings.HF_TOKEN,
        enable_diarization=settings.ENABLE_DIARIZATION,
    )

    return {
        "meeting_id": meeting_id,
        "status": "uploaded",
        "message": "변환이 시작되었습니다. /api/audio/status/{meeting_id} 로 진행 상태를 확인하세요.",
    }


@router.get("/status/{meeting_id}")
def get_status(meeting_id: int):
    """
    변환 진행 상태를 조회합니다.
    프론트에서 폴링 (2~3초 간격)으로 호출.

    status 값:
      - uploaded: 업로드 완료, 변환 대기
      - processing: ffmpeg 전처리 중
      - transcribing: whisperX STT 변환 중
      - diarizing: 화자 분리 중
      - saving: DB 저장 중
      - completed: 변환 완료
      - failed: 변환 실패
    """
    status_info = get_job_status(meeting_id)

    if status_info["status"] == "unknown":
        raise HTTPException(status_code=404, detail="해당 회의를 찾을 수 없습니다.")

    return {
        "meeting_id": meeting_id,
        "status": status_info["status"],
        "progress_message": status_info.get("message", ""),
    }


@router.get("/result/{meeting_id}")
def get_result(meeting_id: int):
    """
    변환 완료된 결과를 조회합니다.
    - segments: 각 발화의 시작/끝/화자/텍스트
    - full_text: D(요약/RAG)가 사용할 전체 텍스트
    """
    status_info = get_job_status(meeting_id)

    if status_info["status"] == "unknown":
        raise HTTPException(status_code=404, detail="해당 회의를 찾을 수 없습니다.")

    if status_info["status"] != "completed":
        raise HTTPException(
            status_code=202,
            detail=f"아직 변환 중입니다. 현재 상태: {status_info['status']}",
        )

    return {
        "meeting_id": meeting_id,
        "status": "completed",
        "document_id": status_info.get("document_id"),
        "segments": status_info.get("segments", []),
        "full_text": status_info.get("full_text", ""),
    }


@router.get("/list")
def list_meetings():
    """
    전체 회의 목록 조회.
    각 회의의 변환 상태를 메모리에서 병합해서 반환.
    """
    from app.database import SessionLocal
    from app.models_meeting import Meeting

    db = SessionLocal()
    try:
        meetings = db.query(Meeting).order_by(Meeting.created_at.desc()).all()
        result = []
        for m in meetings:
            status_info = get_job_status(m.id)
            result.append({
                "meeting_id": m.id,
                "title": m.title,
                "status": status_info.get("status", "unknown"),
                "transcript_document_id": m.transcript_document_id,
                "summary_document_id": m.summary_document_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })
        return result
    finally:
        db.close()
