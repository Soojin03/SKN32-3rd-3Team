from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routers import api

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Meeting Tree Notes (Standard User Only)")

app.include_router(api.router, prefix="/api")
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")