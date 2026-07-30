def extract_text_from_file(file_path: str) -> str:
    """텍스트/로그 파일 등의 내용을 추출하는 스텁 유틸리티"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"파일 읽기 오류: {str(e)}"