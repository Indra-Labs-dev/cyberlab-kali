from app.tools.parsers.nikto import parse_nikto
from app.tools.parsers.nmap import parse_nmap
from app.tools.parsers.whatweb import parse_whatweb

PARSERS = {
    "nmap": parse_nmap,
    "whatweb": parse_whatweb,
    "nikto": parse_nikto,
}


def parse_output(parser_name: str, raw_output: str) -> dict:
    parser = PARSERS.get(parser_name)
    if parser is None:
        return {"raw": raw_output}
    return parser(raw_output)
