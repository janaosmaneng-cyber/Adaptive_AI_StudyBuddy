from typing import List, Optional
from pydantic import BaseModel, Field

class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    max_length: int = Field(default=300, ge=1, le=2000)

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    k: int = Field(default=4, ge=1, le=10)
    max_new_tokens: int = Field(default=400, ge=1, le=2000)

class QuizRequest(BaseModel):
    n: int = Field(default=5, ge=1, le=10)
    topic_id: Optional[str] = Field(default=None, max_length=300)  # from /topics
    topic: Optional[str] = Field(default=None, max_length=500)     # free-text search
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    avoid_questions: List[str] = Field(default_factory=list, max_length=50)

class QuizQuestion(BaseModel):
    question: str = Field(min_length=1)
    options: List[str]
    answer_index: int = Field(ge=0, le=3)
    topic: str
    difficulty: str
    explanation: str
    source_page: Optional[int] = None
    topic_id: Optional[str] = None

class FlashcardRequest(BaseModel):
    n: int = Field(default=8, ge=1, le=15)
    topic_id: Optional[str] = Field(default=None, max_length=300)
    avoid_fronts: List[str] = Field(default_factory=list, max_length=50)

class Flashcard(BaseModel):
    front: str = Field(min_length=1, max_length=400)
    back: str = Field(min_length=1, max_length=800)
    source_page: Optional[int] = None
    topic_id: Optional[str] = None
    topic: Optional[str] = None
