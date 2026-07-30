from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse, Token, DocumentCreate, DocumentUpdate, DocumentResponse, GeminiRequest
from app.services import auth_service, document_service, gemini_service
from app.core.security import decode_access_token

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없거나 비활성화되었습니다.")
    return user

# AUTH API
@router.post("/auth/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register_user(db, user_data)

@router.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return auth_service.authenticate_user(db, form_data.username, form_data.password)

@router.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# DOCUMENT TREE API
@router.post("/documents", response_model=DocumentResponse)
def create_doc(doc_data: DocumentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return document_service.create_document(db, user, doc_data)

@router.get("/documents", response_model=List[DocumentResponse])
def get_docs_by_parent(parent_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return document_service.get_documents_by_parent(db, user, parent_id)

@router.get("/documents/tree")
def get_doc_tree(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return document_service.get_document_tree(db, user)

@router.put("/documents/{doc_id}", response_model=DocumentResponse)
def update_doc(doc_id: int, doc_data: DocumentUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return document_service.update_document(db, user, doc_id, doc_data)

@router.delete("/documents/{doc_id}", status_code=204)
def delete_doc(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document_service.delete_document(db, user, doc_id)

# GEMINI API
@router.post("/gemini/summarize")
def summarize_text(req: GeminiRequest, user: User = Depends(get_current_user)):
    summary = gemini_service.generate_summary(req.prompt)
    return {"summary": summary}