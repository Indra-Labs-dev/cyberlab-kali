import json


def parse_searchsploit(raw_output: str) -> dict:
    text = raw_output.strip()
    if not text:
        return {"exploits": []}

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"exploits": [], "parse_error": True}

    exploits = [
        {
            "title": entry.get("Title"),
            "path": entry.get("Path"),
            "edb_id": entry.get("EDB-ID"),
            "date": entry.get("Date_Published"),
            "type": entry.get("Type"),
        }
        for entry in data.get("RESULTS_EXPLOIT", [])
    ]
    return {"exploits": exploits}
