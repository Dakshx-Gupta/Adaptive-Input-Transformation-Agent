import json

def parse_llm_reply(text):
    """Return (payload, ambiguities, error). Exactly one of payload/error is meaningful."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None, [], "The reply contained no JSON object."
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        return None, [], f"The reply was not valid JSON: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
        return None, [], "The JSON must be an object with a 'payload' object inside it."
    ambiguities = [str(a) for a in data.get("ambiguities", []) if a]
    return data["payload"], ambiguities, None
