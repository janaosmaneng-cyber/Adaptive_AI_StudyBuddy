from services.model_service import generate_text
from services.vector_store import store


def clean_label(raw):
    """Keep the first line of the model response as a short topic title."""
    lines = raw.strip().splitlines()
    label = lines[0].strip().strip(" *#`").strip(chr(34)).strip(chr(39)).rstrip(".:")
    return label[:60]


def label_topics_for_document(document_name):
    """Give each topic a short title; retain the page-range fallback if generation fails."""
    for topic in store.topics_for_doc(document_name):
        chunks = store.chunks_for_topic(topic["id"])
        sample = " ".join(chunk["text"] for chunk in chunks[:3])[:1800]
        try:
            title = generate_text(
                [
                    {
                        "role": "system",
                        "content": "Give this study section a title of 2 to 5 words. Return the title only.",
                    },
                    {"role": "user", "content": f"Passages:\n{sample}"},
                ],
                max_new_tokens=16,
                temperature=0,
            )
            title = clean_label(title)
        except Exception:
            title = ""

        if title:
            store.topics[topic["id"]]["label"] = title


def tag_item_topic(item, context_chunks, topic_id=None):
    """Attach a stable topic ID and topic label to a generated item."""
    # If the caller selected a topic, use it directly.
    if topic_id is None:
        # Prefer the topic matching the generated source page.
        page = item.get("source_page")
        matching = [chunk for chunk in context_chunks if chunk["page"] == page]
        if not matching:
            matching = context_chunks

        # Fall back to the first context chunk so the ID is never missing
        # when the context came from an indexed PDF.
        for chunk in matching:
            if chunk.get("topic_id"):
                topic_id = chunk["topic_id"]
                break

    item["topic_id"] = topic_id
    if topic_id in store.topics:
        item["topic"] = store.topics[topic_id]["label"]
    return item
