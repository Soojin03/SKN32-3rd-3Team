"""
오디오 전처리 서비스 — 역할 C
ffmpeg 를 이용해 업로드된 오디오를 Whisper 입력에 최적화된 형식으로 변환.
"""

import subprocess
import os


def preprocess_audio(input_path: str) -> str:
    """
    오디오 파일을 WAV 16kHz mono 로 변환.
    - Whisper 권장 입력 형식
    - 원본 파일은 유지, 변환본은 _16k.wav 접미사로 생성

    Args:
        input_path: 원본 오디오 파일 경로

    Returns:
        변환된 파일 경로

    Raises:
        subprocess.CalledProcessError: ffmpeg 실행 실패 시
    """
    output_path = input_path.rsplit(".", 1)[0] + "_16k.wav"

    # 이미 변환된 파일이 있으면 스킵
    if os.path.exists(output_path):
        return output_path

    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-ar", "16000",     # 16kHz 샘플링
        "-ac", "1",         # mono
        "-c:a", "pcm_s16le",  # 16bit PCM
        "-y",               # 덮어쓰기
        output_path,
    ]

    subprocess.run(
        cmd,
        capture_output=True,
        check=True,
        timeout=300,  # 5분 타임아웃
    )

    return output_path


def validate_audio_file(filename: str, file_size: int, allowed_extensions: str, max_size_mb: int) -> str | None:
    """
    업로드 파일 검증.

    Returns:
        에러 메시지 (없으면 None)
    """
    # 확장자 검증
    ext = os.path.splitext(filename)[1].lower()
    allowed = [e.strip() for e in allowed_extensions.split(",")]
    if ext not in allowed:
        return f"지원하지 않는 형식입니다. 허용: {', '.join(allowed)}"

    # 크기 검증
    max_bytes = max_size_mb * 1024 * 1024
    if file_size > max_bytes:
        return f"파일 크기가 {max_size_mb}MB를 초과합니다."

    return None


def cleanup_processed_file(input_path: str):
    """변환된 임시 파일 삭제"""
    processed = input_path.rsplit(".", 1)[0] + "_16k.wav"
    if os.path.exists(processed):
        os.remove(processed)
