from fastapi import APIRouter, Depends
from auth import check_api_key
from services.vector_store import store

router = APIRouter()

@router.get("/topics", dependencies=[Depends(check_api_key)])
def list_topics():
    """Return the topics created when PDFs were uploaded."""
    return {"topics": store.list_topics()}
