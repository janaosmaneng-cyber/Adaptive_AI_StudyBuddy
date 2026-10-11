import json
import re

def get_json_array(text):
    """Parse a JSON list, including when the model wraps it in code fences."""
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        result = json.loads(cleaned[start:end + 1])
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []
