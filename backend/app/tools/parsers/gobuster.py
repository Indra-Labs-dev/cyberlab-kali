import re

_LINE_PATTERN = re.compile(r"^(?P<path>\S+)\s+\(Status:\s*(?P<status>\d+)\)\s*\[Size:\s*(?P<size>\d+)\]")


def parse_gobuster(raw_output: str) -> dict:
    results = []
    for line in raw_output.splitlines():
        match = _LINE_PATTERN.match(line.strip())
        if not match:
            continue
        results.append(
            {
                "path": match.group("path"),
                "status": int(match.group("status")),
                "size": int(match.group("size")),
            }
        )
    return {"results": results}
