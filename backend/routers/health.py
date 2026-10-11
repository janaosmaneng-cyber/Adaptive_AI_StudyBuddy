import torch
from fastapi import APIRouter
from config import LLM_NAME, QUANT
from services.model_service import llm, model_memory_footprint_gb
from services.vector_store import store

router = APIRouter()

@router.get("/health")
def health():
    gpu_memory_by_device = {}
    if torch.cuda.is_available():
        for device_id in range(torch.cuda.device_count()):
            gpu_memory_by_device[f"cuda:{device_id}"] = round(
                torch.cuda.memory_allocated(device_id) / (1024 ** 3), 2
            )

    return {
        "status": "ok",
        "model": LLM_NAME,
        "quantization": QUANT,
        "model_memory_footprint_gb": model_memory_footprint_gb(),
        "gpu_allocated_memory_gb_by_device": gpu_memory_by_device,
        "chunks_indexed": len(store.chunks),
        "documents": sorted({chunk["doc"] for chunk in store.chunks}),
    }
