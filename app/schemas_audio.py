"""
Audio 관련 Pydantic 스키마 — 역할 C 담당
기존 schemas.py 하단에 병합하세요.
"""

from pydantic import BaseModel
from datetime import datetime


# ── 요청 ──

class MeetingCreate(BaseModel):
    """오디오 업로드 시 함께 보내는 메타데이터"""
    title: str = "제목 없는 회의"


# ── 응답 ──

class AudioUploadResponse(BaseModel):
    """업로드 직후 반환"""
    meeting_id: int
    status: str  # uploaded

    model_config = {"from_attributes": True}


class JobStatusResponse(BaseModel):
    """잡 상태 조회 응답"""
    meeting_id: int
    status: str  # uploaded | processing | transcribing | diarizing | completed | failed
    progress_message: str | None = None

    model_config = {"from_attributes": True}


class TranscriptSegment(BaseModel):
    """개별 발화 세그먼트"""
    start: float
    end: float
    speaker: str | None = None
    text: str


class TranscriptResponse(BaseModel):
    """변환 완료 후 전체 결과 조회"""
    meeting_id: int
    title: str
    status: str
    segments: list[TranscriptSegment] = []
    full_text: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
