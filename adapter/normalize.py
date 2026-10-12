def normalize(payload, schema):
    props = schema.get("properties", {})
    cleaned = {}
    for key, value in payload.items():
        value = _coerce(value, props.get(key, {}))
        if value is None or value == "":
            continue                       # treat as missing
        cleaned[key] = value
    return cleaned

def _coerce(value, spec):
    t = spec.get("type")
    if isinstance(value, str):
        value = value.strip()
        if t == "string" and "enum" in spec:
            for allowed in spec["enum"]:
                if value.lower() == str(allowed).lower():
                    return allowed
        if t == "integer":
            try: return int(value)
            except ValueError: pass
        if t == "number":
            try: return float(value)
            except ValueError: pass
        if t == "boolean" and value.lower() in ("true", "false"):
            return value.lower() == "true"
    if t == "object" and isinstance(value, dict):
        return normalize(value, spec)
    return value
