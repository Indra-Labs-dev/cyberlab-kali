from app.tools.parsers.gobuster import parse_gobuster
from app.tools.parsers.masscan import parse_masscan
from app.tools.parsers.nikto import parse_nikto
from app.tools.parsers.nmap import parse_nmap
from app.tools.parsers.nuclei import parse_nuclei
from app.tools.parsers.searchsploit import parse_searchsploit
from app.tools.parsers.sslscan import parse_sslscan
from app.tools.parsers.whatweb import parse_whatweb

PARSERS = {
    "nmap": parse_nmap,
    "whatweb": parse_whatweb,
    "nikto": parse_nikto,
    "masscan": parse_masscan,
    "gobuster": parse_gobuster,
    "nuclei": parse_nuclei,
    "sslscan": parse_sslscan,
    "searchsploit": parse_searchsploit,
}


def parse_output(parser_name: str, raw_output: str) -> dict:
    parser = PARSERS.get(parser_name)
    if parser is None:
        return {"raw": raw_output}
    return parser(raw_output)
