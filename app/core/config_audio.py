"""
core/config.py 의 Settings 클래스에 아래 필드를 추가하세요.
─────────────────────────────────────────────
class Settings(BaseSettings):
    # ... 기존 MySQL, JWT 설정 ...

    # ── Audio / WhisperX (C 담당) ──
    UPLOAD_DIR: str = "uploads"
    WHISPER_MODEL: str = "medium"          # tiny | small | medium | large-v3
    WHISPER_DEVICE: str = "cuda"           # cuda | cpu
    HF_TOKEN: str = ""                     # pyannote 화자분리용 HuggingFace 토큰
    ENABLE_DIARIZATION: bool = True        # False 면 화자분리 생략 (빠른 개발용)
    MAX_AUDIO_SIZE_MB: int = 100           # 업로드 최대 크기
    ALLOWED_AUDIO_EXTENSIONS: str = ".mp3,.wav,.m4a,.webm,.ogg,.flac"

─────────────────────────────────────────────

.env.example 에도 아래를 추가:

# ── Audio (C 담당) ──
UPLOAD_DIR=uploads
WHISPER_MODEL=medium
WHISPER_DEVICE=cuda
HF_TOKEN=hf_your_token_here
ENABLE_DIARIZATION=true
MAX_AUDIO_SIZE_MB=100
ALLOWED_AUDIO_EXTENSIONS=.mp3,.wav,.m4a,.webm,.ogg,.flac
"""
