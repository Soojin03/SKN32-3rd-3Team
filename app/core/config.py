from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # .env 파일에서 자동으로 매핑되어 채워지는 변수들
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 기본값 1일 (분 단위)
    GEMINI_API_KEY: str = ""

    # .env 파일을 최우선으로 읽어오도록 설정
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # .env에 클래스 정의 외의 추가 변수가 있어도 무시
    )

settings = Settings()