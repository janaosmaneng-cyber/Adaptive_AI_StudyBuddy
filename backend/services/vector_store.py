import random
import faiss
from config import CHUNK_WORDS, CHUNK_OVERLAP, MAX_TOPICS_PER_DOC, CHUNKS_PER_TOPIC
from services.model_service import embedder

class DocumentStore:
    """In-memory FAISS index, extracted PDF chunks, and their topics."""

    def __init__(self):
        self.reset()

    def reset(self):
        dimension = embedder.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatIP(dimension)
        self.chunks = []
        self.topics = {}  # topic_id -> {"id", "doc", "label", "pages", "n_chunks"}

    def documents(self):
        return {chunk["doc"] for chunk in self.chunks}

    def add_pdf_pages(self, document_name, pages):
        first_new_chunk = len(self.chunks)
        new_chunks = []
        step = CHUNK_WORDS - CHUNK_OVERLAP

        for page_number, page_text in enumerate(pages, start=1):
            words = page_text.split()
            for start in range(0, len(words), step):
                chunk_words = words[start:start + CHUNK_WORDS]
                if len(chunk_words) < 15:
                    continue
                new_chunks.append({
                    "doc": document_name,
                    "page": page_number,
                    "text": " ".join(chunk_words),
                    "topic_id": None,
                })

        if not new_chunks:
            return 0

        vectors = embedder.encode(
            [chunk["text"] for chunk in new_chunks],
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")

        self.index.add(vectors)
        self.chunks.extend(new_chunks)
        self._assign_topics(document_name, first_new_chunk)
        return len(new_chunks)

    def _assign_topics(self, document_name, first_chunk_index):
        """Split a document's chunks, in reading order, into equal topic groups.

        Deterministic on purpose: the same PDF always gives the same topic ids,
        so a student's saved progress still matches after a server restart.
        """
        doc_chunks = self.chunks[first_chunk_index:]
        total = len(doc_chunks)
        topic_count = max(1, min(MAX_TOPICS_PER_DOC, total // CHUNKS_PER_TOPIC))

        for position, chunk in enumerate(doc_chunks):
            group = min(topic_count - 1, position * topic_count // total)
            topic_id = f"{document_name}#{group + 1}"
            chunk["topic_id"] = topic_id

            topic = self.topics.setdefault(topic_id, {
                "id": topic_id,
                "doc": document_name,
                "label": "",
                "pages": [chunk["page"], chunk["page"]],
                "n_chunks": 0,
            })
            topic["pages"][0] = min(topic["pages"][0], chunk["page"])
            topic["pages"][1] = max(topic["pages"][1], chunk["page"])
            topic["n_chunks"] += 1

        # Fallback label; the model replaces it with a real title afterwards.
        for topic in self.topics_for_doc(document_name):
            first_page, last_page = topic["pages"]
            topic["label"] = (
                f"Page {first_page}" if first_page == last_page
                else f"Pages {first_page}-{last_page}"
            )

    def topics_for_doc(self, document_name):
        return [t for t in self.topics.values() if t["doc"] == document_name]

    def list_topics(self):
        return list(self.topics.values())

    def chunks_for_topic(self, topic_id):
        return [chunk for chunk in self.chunks if chunk["topic_id"] == topic_id]

    def search(self, question, number=4):
        if not self.chunks:
            return []

        query_vector = embedder.encode(
            [question],
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")

        scores, ids = self.index.search(
            query_vector,
            min(number, len(self.chunks)),
        )
        results = []
        for score, chunk_id in zip(scores[0], ids[0]):
            if chunk_id >= 0:
                item = self.chunks[chunk_id].copy()
                item["score"] = float(score)
                results.append(item)
        return results

    def random_chunks(self, number=5):
        return random.sample(self.chunks, min(number, len(self.chunks)))

store = DocumentStore()

def format_context(chunks):
    return "\n\n".join(
        f"[Document: {chunk['doc']} | Page {chunk['page']}]\n{chunk['text']}"
        for chunk in chunks
    )
