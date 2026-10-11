from fastapi import APIRouter, Depends
from auth import check_api_key
from schemas import GenerateRequest
from services.model_service import generate_text

router = APIRouter()

@router.post("/generate", dependencies=[Depends(check_api_key)])
def generate(request: GenerateRequest):
    answer = generate_text(
        [{"role": "user", "content": request.prompt}],
        max_new_tokens=request.max_length,
    )
    return {"response": answer}
