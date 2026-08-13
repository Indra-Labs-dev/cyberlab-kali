import json


def render(data: dict, template: str = "technical") -> str:
    # JSON is a full-fidelity data export for downstream tooling, not a
    # "view" -- it always dumps the complete data dict regardless of
    # template, so no report data is ever silently dropped from this format.
    return json.dumps(data, indent=2)
