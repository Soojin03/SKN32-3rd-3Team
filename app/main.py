from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import api
from app.routers import audio
from app.models_meeting import Meeting  # meetings 테이블 자동 생성용

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Meeting Tree Notes (Standard User Only)")

app.include_router(api.router, prefix="/api")
app.include_router(audio.router)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")