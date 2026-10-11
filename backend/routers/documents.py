from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from auth import check_api_key
from config import MAX_PDF_MB
from services.pdf_service import read_and_index_pdf
from services.vector_store import store

router = APIRouter()

@router.post("/ingest", dependencies=[Depends(check_api_key)])
def ingest(file: UploadFile = File(...)):
    # Check the name before reading or processing the file.
    filename = file.filename
    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    if filename in store.documents():
        raise HTTPException(
            status_code=409,
            detail=f"'{filename}' is already indexed. Call /reset first to start over.",
        )

    # Read at most one byte over the limit, so a huge upload isn't read fully into RAM.
    max_bytes = MAX_PDF_MB * 1024 * 1024
    file_bytes = file.file.read(max_bytes + 1)
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"PDF is too large. Maximum size is {MAX_PDF_MB} MB.",
        )

    # The service extracts text, indexes chunks, and creates topic labels.
    return read_and_index_pdf(filename, file_bytes)


@router.post("/reset", dependencies=[Depends(check_api_key)])
def reset_index():
    """Clear all indexed PDFs, chunks, and topics."""
    store.reset()
    return {"status": "cleared", "chunks_indexed": 0, "topics_cleared": True}
