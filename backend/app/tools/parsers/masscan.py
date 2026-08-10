import json


def parse_masscan(raw_output: str) -> dict:
    text = raw_output.strip()
    if not text:
        return {"hosts": []}

    # masscan's -oJ output can end up truncated (no closing ']') if the
    # process is killed by our own timeout mid-scan -- repair a trailing
    # dangling comma/record rather than failing outright on partial output.
    if not text.startswith("["):
        text = "[" + text
    if not text.endswith("]"):
        text = text.rstrip(",\n\r ") + "]"

    try:
        records = json.loads(text)
    except json.JSONDecodeError:
        return {"hosts": [], "parse_error": True}

    hosts = []
    for record in records:
        if not isinstance(record, dict):
            continue
        ports = [
            {"port": p.get("port"), "protocol": p.get("proto"), "state": p.get("status")}
            for p in record.get("ports", [])
        ]
        hosts.append({"address": record.get("ip"), "ports": ports})
    return {"hosts": hosts}
