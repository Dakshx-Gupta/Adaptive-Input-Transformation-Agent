from jsonschema import Draft202012Validator, FormatChecker

def schema_problems(payload, schema):
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    problems = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        field = ".".join(str(p) for p in err.path)
        if err.validator == "required":
            for name in err.validator_value:
                if name not in err.instance:
                    problems.append({"kind": "missing", "field": name,
                                     "message": f"'{name}' is required but was not found."})
        elif err.validator == "minProperties":
            problems.append({"kind": "missing", "field": field,
                             "message": f"'{field}' must not be empty."})
        else:
            problems.append({"kind": "invalid", "field": field or "(root)",
                             "message": err.message})
    return problems

def grounding_problems(payload, schema, raw_text):
    haystack = " ".join(raw_text.lower().split())
    problems = []
    for field, spec in schema.get("properties", {}).items():
        if spec.get("x-verbatim") and field in payload:
            value = " ".join(str(payload[field]).lower().split())
            if value not in haystack:
                problems.append({"kind": "invalid", "field": field,
                    "message": f"'{payload[field]}' does not appear in the input; "
                    f"critical values must not be invented."})
    return problems

def validate(payload, schema, raw_text):
    return schema_problems(payload, schema) + grounding_problems(payload, schema, raw_text)
