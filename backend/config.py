import os

API_KEY = os.getenv("API_KEY", "")


LLM_NAME = os.getenv(
    "LLM_NAME",
    #  "mistralai/Mistral-Nemo-Instruct-2407",
      "Qwen/Qwen2.5-0.5B-Instruct",
    # "Qwen/Qwen2.5-7B-Instruct",
    # "Qwen/Qwen2.5-3B-Instruct",
)
EMB_NAME = os.getenv(
    "EMB_NAME",
    "BAAI/bge-m3",
)
QUANT = os.getenv("QUANT", "4bit").lower()

CHUNK_WORDS = 150
CHUNK_OVERLAP = 25

MAX_PDF_MB = int(os.getenv("MAX_PDF_MB", "30"))

# Phase 2: every PDF is split into topics (consecutive groups of chunks).
MAX_TOPICS_PER_DOC = int(os.getenv("MAX_TOPICS_PER_DOC", "8"))
CHUNKS_PER_TOPIC = 4  # a topic gets at least this many chunks on average
