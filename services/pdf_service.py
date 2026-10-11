from io import BytesIO
from PyPDF2 import PdfReader
from fastapi import HTTPException
from services.topic_service import label_topics_for_document
from services.vector_store import store

def read_and_index_pdf(filename, file_bytes):
    """Extract text from a text-based PDF, index it for RAG, and build its topics."""
    if filename in store.documents():
        raise HTTPException(
            status_code=409,
            detail=f"'{filename}' is already indexed. Call /reset first to start over.",
        )

    try:
        reader = PdfReader(BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}")

    added_chunks = store.add_pdf_pages(filename, pages)
    if added_chunks == 0:
        raise HTTPException(
            status_code=422,
            detail="No readable text found. Scanned PDFs need OCR first.",
        )

    label_topics_for_document(filename)

    return {
        "document": filename,
        "pages": len(pages),
        "chunks_added": added_chunks,
        "total_chunks": len(store.chunks),
        "topics": store.topics_for_doc(filename),
    }
