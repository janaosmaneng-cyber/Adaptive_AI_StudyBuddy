"""Tiny client for the AdaptiveAI backend (the FastAPI server on Kaggle, via ngrok)."""
import requests


class ApiError(Exception):
    """Raised for any backend problem. status == 0 means the server was unreachable."""

    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail

    def __str__(self):
        return self.detail


class Backend:
    def __init__(self, base_url, api_key):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {(api_key or '').strip()}",
            # ngrok's free tier shows an HTML warning page unless this header is sent.
            "ngrok-skip-browser-warning": "1",
        }

    def _call(self, method, path, timeout, **kwargs):
        if not self.base_url:
            raise ApiError(0, "Paste your backend (ngrok) URL in the sidebar first.")
        try:
            response = requests.request(
                method, self.base_url + path, headers=self.headers, timeout=timeout, **kwargs
            )
        except requests.exceptions.Timeout:
            raise ApiError(0, "The server took too long to answer. The model may still be busy - try again.")
        except requests.exceptions.RequestException as exc:
            raise ApiError(0, f"Can't reach the backend ({exc.__class__.__name__}). Is the Kaggle notebook running?")

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text[:200] or "Unknown error"
            if isinstance(detail, list):  # FastAPI validation errors
                detail = "; ".join(str(item.get("msg", item)) for item in detail)
            raise ApiError(response.status_code, str(detail))
        try:
            return response.json()
        except ValueError:
            raise ApiError(response.status_code, "The server did not return JSON (is this the right URL?).")

    # ---- endpoints -------------------------------------------------------
    def health(self):
        return self._call("GET", "/health", 20)

    def topics(self):
        return self._call("GET", "/topics", 30)

    def ingest(self, filename, file_bytes):
        files = {"file": (filename, file_bytes, "application/pdf")}
        return self._call("POST", "/ingest", 900, files=files)

    def reset(self):
        return self._call("POST", "/reset", 30)

    def chat(self, question, k=4, max_new_tokens=400):
        body = {"question": question, "k": k, "max_new_tokens": max_new_tokens}
        return self._call("POST", "/chat", 300, json=body)

    def quiz(self, n, topic_id=None, difficulty="medium", avoid_questions=None):
        body = {"n": n, "difficulty": difficulty, "avoid_questions": (avoid_questions or [])[:50]}
        if topic_id:
            body["topic_id"] = topic_id
        return self._call("POST", "/quiz", 600, json=body)

    def flashcards(self, n, topic_id=None, avoid_fronts=None):
        body = {"n": n, "avoid_fronts": (avoid_fronts or [])[:50]}
        if topic_id:
            body["topic_id"] = topic_id
        return self._call("POST", "/flashcards", 600, json=body)
