import re


def summarize(text, limit=500):
    """Extractive summary: the opening sentences of the article, within a length limit."""
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned

    window = cleaned[:limit]
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence_end >= 80:
        return window[: sentence_end + 1].strip()
    return window.rsplit(" ", 1)[0].strip() + "..."
