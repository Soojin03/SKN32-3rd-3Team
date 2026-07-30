"""
main.py 에 추가할 코드 — 역할 C

아래 두 가지를 기존 main.py 에 추가하세요.
──────────────────────────────────────────────

1) import 추가:
"""
from app.routers import audio         # ← C 추가
from app.models_meeting import Meeting  # ← 테이블 자동 생성용

"""
2) 라우터 등록 (기존 app.include_router(api.router) 근처에):
"""
# app.include_router(audio.router)     # ← C 추가

"""
3) DB 테이블 자동 생성 부분에 Meeting 모델 import 확인:
   기존에 Base.metadata.create_all(bind=engine) 가 있다면,
   Meeting 모델이 import 된 상태에서 실행되면 meetings 테이블이 자동 생성됩니다.
   
   만약 models.py 의 Base 와 models_meeting.py 의 Base 가 다르면
   테이블이 안 만들어질 수 있으니, 반드시 같은 Base 를 사용하세요.
   
   models_meeting.py 상단의:
     Base = declarative_base()  # ← 이 줄을 삭제하고
   
   대신:
     from app.database import Base  # ← 기존 Base import
   
   로 바꿔야 합니다.
"""
