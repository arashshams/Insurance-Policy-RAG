"""
api_client.py — the Streamlit app's HTTP client for the FastAPI backend.

Used when INSURANCE_RAG_API_URL is set (demo mode served by the deployed API,
PLAN.md M4). Kept framework-free (no Streamlit import) so it can be tested
offline. Turns transport and HTTP errors into short messages a visitor can
understand, and normalizes the reply to the shape the UI already renders
(the same fields as rag_pipeline.answer_question_detailed).
"""

from __future__ import annotations

from typing import Any

# The deployed API scales to zero when idle (the first request after a quiet
# period starts a new instance, a few seconds), and with the fallback model
# (PLAN.md D19) a request can make two generation attempts. 90 s covers both
# and stays inside Cloud Run's 120 s request timeout.
TIMEOUT_S = 90

UNREACHABLE = ("The answer service isn't reachable right now. It may be starting up "
               "after a quiet period; please try again in a moment.")
TIMED_OUT = ("The answer service took too long to respond (it may have been starting "
             "up). Please try again.")


class ApiError(RuntimeError):
    """A message that is safe and useful to show to the visitor."""


def ask(api_url: str, question: str, token: str = "", timeout: float = TIMEOUT_S,
        post=None) -> dict[str, Any]:
    """POST the question to {api_url}/ask and return the normalized result.

    `post` defaults to requests.post; tests pass a fake. Raises ApiError with
    a visitor-friendly message on any failure.
    """
    import requests

    post = post or requests.post
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = post(f"{api_url.rstrip('/')}/ask", json={"question": question},
                    headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise ApiError(TIMED_OUT) from exc
    except requests.RequestException as exc:
        raise ApiError(UNREACHABLE) from exc

    if resp.status_code >= 400:
        # Prefer the API's own explanation (e.g. "the daily quota is used up,
        # try again in about 13 hours") over a bare "503 Server Error".
        try:
            detail = resp.json().get("detail")
        except Exception:  # noqa: BLE001 - non-JSON error body
            detail = None
        if resp.status_code == 401:
            raise ApiError("The app isn't authorized to use the answer service "
                           "(check INSURANCE_RAG_API_TOKEN).")
        if isinstance(detail, str) and detail:
            raise ApiError(detail)
        raise ApiError(f"The answer service returned an error ({resp.status_code}).")

    data = resp.json()
    return {
        "answer": data.get("answer", ""),
        "pages": data.get("pages", []),
        "retrieved": [
            {"id": c.get("id", ""), "text": c.get("text", ""),
             "metadata": {"page": c.get("page")}, "score": c.get("score")}
            for c in data.get("retrieved", [])
        ],
        "abstained": bool(data.get("abstained")),
        "citations_verified": bool(data.get("citations_verified")),
        "model_used": data.get("model"),
        "fallback_used": bool(data.get("fallback_used")),
    }
