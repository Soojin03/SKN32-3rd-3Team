from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Document, User

def validate_parent_id(db: Session, parent_id: Optional[int], owner_id: int):
    if parent_id is not None:
        parent_doc = db.query(Document).filter(Document.id == parent_id, Document.owner_id == owner_id).first()
        if not parent_doc:
            raise HTTPException(status_code=404, detail="상위 문서를 찾을 수 없거나 권한이 없습니다.")

def check_circular_dependency(db: Session, doc_id: int, new_parent_id: int):
    if doc_id == new_parent_id:
        raise HTTPException(status_code=400, detail="자기 자신을 부모 문서로 지정할 수 없습니다.")
    
    current_parent_id = new_parent_id
    while current_parent_id is not None:
        parent_doc = db.query(Document).filter(Document.id == current_parent_id).first()
        if not parent_doc:
            break
        if parent_doc.id == doc_id:
            raise HTTPException(status_code=400, detail="하위 문서를 부모 문서로 지정할 수 없습니다. (순환 참조 방지)")
        current_parent_id = parent_doc.parent_id

def create_document(db: Session, user: User, doc_data) -> Document:
    validate_parent_id(db, doc_data.parent_id, user.id)
    doc = Document(
        owner_id=user.id,
        title=doc_data.title,
        content=doc_data.content,
        summary=doc_data.summary,
        source_type=doc_data.source_type,
        parent_id=doc_data.parent_id
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

def get_documents_by_parent(db: Session, user: User, parent_id: Optional[int] = None) -> List[Document]:
    query = db.query(Document).filter(Document.owner_id == user.id)
    if parent_id is None:
        query = query.filter(Document.parent_id.is_(None))
    else:
        query = query.filter(Document.parent_id == parent_id)
    return query.all()

def build_tree_recursive(doc: Document) -> dict:
    return {
        "id": doc.id,
        "owner_id": doc.owner_id,
        "title": doc.title,
        "content": doc.content,
        "summary": doc.summary,
        "source_type": doc.source_type.value if hasattr(doc.source_type, 'value') else doc.source_type,
        "parent_id": doc.parent_id,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "children": [build_tree_recursive(child) for child in doc.children]
    }

def get_document_tree(db: Session, user: User) -> List[dict]:
    root_docs = db.query(Document).filter(Document.owner_id == user.id, Document.parent_id.is_(None)).all()
    return [build_tree_recursive(doc) for doc in root_docs]

def update_document(db: Session, user: User, doc_id: int, doc_data) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id, Document.owner_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    
    if doc_data.parent_id is not None and doc_data.parent_id != doc.parent_id:
        validate_parent_id(db, doc_data.parent_id, user.id)
        check_circular_dependency(db, doc_id, doc_data.parent_id)
        doc.parent_id = doc_data.parent_id
        
    if doc_data.title is not None:
        doc.title = doc_data.title
    if doc_data.content is not None:
        doc.content = doc_data.content
    if doc_data.summary is not None:
        doc.summary = doc_data.summary

    db.commit()
    db.refresh(doc)
    return doc

def delete_document(db: Session, user: User, doc_id: int):
    doc = db.query(Document).filter(Document.id == doc_id, Document.owner_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    db.delete(doc)
    db.commit()