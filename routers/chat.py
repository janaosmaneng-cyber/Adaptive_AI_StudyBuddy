from fastapi import APIRouter, Depends, HTTPException
from auth import check_api_key
from schemas import ChatRequest
from services.model_service import generate_text
from services.vector_store import store, format_context

router = APIRouter()

@router.post("/chat", dependencies=[Depends(check_api_key)])
def chat(request: ChatRequest):
    matches = store.search(request.question, request.k)
    if not matches:
        raise HTTPException(
            status_code=400,
            detail="No PDF material indexed yet. Call /ingest first.",
        )

    system_message = (
        "You are a study assistant. Answer using only the supplied context. "
        "If the answer is not present, say you could not find it in the material. "
        "Cite the supporting page using (p. N). Do not invent citations."
    )
    user_message = (
        f"Context:\n{format_context(matches)}\n\n"
        f"Question: {request.question}"
    )

    answer = generate_text(
        [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        max_new_tokens=request.max_new_tokens,
    )

    sources = [
        {
            "document": match["doc"],
            "page": match["page"],
            "score": round(match["score"], 3),
            "snippet": match["text"][:200],
        }
        for match in matches
    ]
    return {"answer": answer, "sources": sources}
