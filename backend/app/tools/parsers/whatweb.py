import json


def parse_whatweb(raw_output: str) -> dict:
    results = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, list):
            results.extend(record)
        else:
            results.append(record)
    return {"results": results}
