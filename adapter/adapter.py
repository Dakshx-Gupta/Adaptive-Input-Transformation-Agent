import json
import re

from .normalize import normalize
from .parse import parse_llm_reply
from .prompts import build_prompt
from .validate import validate

# Words that mean "a date relative to today"
RELATIVE_DATE = re.compile(
    r"\b(today|tomorrow|tonight|yesterday|next|last|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


def _result(status, payload=None, missing=None, problems=None, ambiguities=None, message=""):
    """Every result has the same shape, so callers never have to guess."""
    return {
        "status": status,              # "ok" | "needs_clarification" | "error"
        "payload": payload,
        "missing_fields": missing or [],
        "problems": problems or [],
        "ambiguities": ambiguities or [],
        "message": message,
        "dry_run": True,               # nothing is ever executed
    }


def _needs_reference_date(raw_text, schema, context):
    """If the schema has a date field and the text says 'tomorrow' (etc.)
    but we were not told today's date, ask instead of guessing."""
    has_date_field = any(
        spec.get("format") == "date" for spec in schema.get("properties", {}).values()
    )
    if has_date_field and RELATIVE_DATE.search(raw_text) and context.reference_date is None:
        return _result(
            "needs_clarification",
            missing=["reference_date"],
            message="The input uses a relative date, but no reference date was provided.",
        )
    return None


def _build_result(payload, problems, ambiguities):
    missing = [p["field"] for p in problems if p["kind"] == "missing"]
    invalid = [p for p in problems if p["kind"] == "invalid"]

    if invalid:
        return _result("error", missing=missing, problems=problems,
                       ambiguities=ambiguities, message="The payload is invalid.")
    if missing or ambiguities:
        return _result("needs_clarification", payload=payload or None, missing=missing,
                       problems=problems, ambiguities=ambiguities,
                       message="More information is needed before this can be forwarded.")
    return _result("ok", payload=payload)


def adapt(raw_input, contract, context, llm, max_attempts=3):
    """Convert raw_input into a payload matching contract's schema.
    Works for ANY contract. Contains no agent-specific logic."""
    schema = contract["schema"]
    raw_text = raw_input if isinstance(raw_input, str) else json.dumps(raw_input, ensure_ascii=False)

    early = _needs_reference_date(raw_text, schema, context)
    if early:
        return early

    payload, problems, ambiguities = {}, [], []
    for _ in range(max_attempts):
        reply = llm.complete(build_prompt(raw_text, contract, context, problems))
        parsed, ambiguities, parse_error = parse_llm_reply(reply)

        if parse_error:
            problems = [{"kind": "invalid", "field": "(reply)", "message": parse_error}]
            continue                                   # retry

        payload = normalize(parsed, schema)
        problems = validate(payload, schema, raw_text)

        if not problems:
            break                                      # success
        if all(p["kind"] == "missing" for p in problems):
            break                                      # retrying a missing field only invites invention

    return _build_result(payload, problems, ambiguities)
