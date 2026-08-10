import json


def render(data: dict) -> str:
    return json.dumps(data, indent=2)
