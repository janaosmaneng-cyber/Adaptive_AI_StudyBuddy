from fastapi import FastAPI
from routers import health, generate, documents, chat, quiz, topics, flashcards

app = FastAPI(title="AdaptiveAI - Phase 2")

app.include_router(health.router)
app.include_router(generate.router)
app.include_router(documents.router)
app.include_router(topics.router)
app.include_router(chat.router)
app.include_router(quiz.router)
app.include_router(flashcards.router)

@app.get("/")
def home():
    return {
        "message": "AdaptiveAI API is running",
        "docs": "/docs",
        "health": "/health",
    }
