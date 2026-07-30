"""
Meeting ORM 모델 — 역할 C 담당
기존 models.py 의 Base, User, Document 를 import 해서 사용.
이 파일의 내용을 models.py 하단에 병합하거나, 별도 파일로 유지 후 main.py 에서 import.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func

# ──────────────────────────────────────────────
# 기존 models.py 에서 Base 를 가져옴
# from app.database import Base
# ──────────────────────────────────────────────
# 단독 실행 / 테스트 편의를 위해 아래처럼 선언해두고,
# 실제 병합 시 기존 Base 를 사용하세요.
from app.database import Base  # 기존 Base 사용


class Meeting(Base):
    """
    meetings 테이블 (제안 → 구현)
    - owner_id  : 회의 등록 유저
    - audio_path: 업로드된 오디오 파일 경로
    - transcript_document_id: whisperX 변환 결과가 저장된 documents.id (nullable)
    - summary_document_id   : LLM 요약 결과가 저장된 documents.id   (nullable, D 담당)
    - status 컬럼 없음 — 메모리(dict)로 관리 (스키마 설계 문서 확정)
    """
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    audio_path = Column(String(500), nullable=True)

    # 변환 완료 후 C 가 연결
    transcript_document_id = Column(
        Integer, ForeignKey("documents.id"), nullable=True
    )
    # 요약 완료 후 D 가 연결
    summary_document_id = Column(
        Integer, ForeignKey("documents.id"), nullable=True
    )

    created_at = Column(DateTime, server_default=func.now())
