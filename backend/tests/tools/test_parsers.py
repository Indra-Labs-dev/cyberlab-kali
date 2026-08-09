from app.tools.parsers.nikto import parse_nikto
from app.tools.parsers.nmap import parse_nmap
from app.tools.parsers.whatweb import parse_whatweb

NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="127.0.0.1" addrtype="ipv4"/>
    <hostnames><hostname name="localhost" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="9000">
        <state state="open"/>
        <service name="cslistener" product="" version=""/>
      </port>
    </ports>
  </host>
</nmaprun>
"""

NMAP_XML_XXE = """<?xml version="1.0"?>
<!DOCTYPE nmaprun [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="&xxe;" addrtype="ipv4"/>
  </host>
</nmaprun>
"""

WHATWEB_JSON = (
    '[{"target":"http://10.0.0.1","http_status":200,"plugins":{"HTTPServer":{"string":["nginx"]}}}]\n'
)

NIKTO_TXT = """- Nikto v2.5.0
---------------------------------------------------------------------------
+ Target IP:          10.0.0.1
+ Target Hostname:    10.0.0.1
+ Target Port:        80
+ Start Time:         2026-08-09 23:00:00
---------------------------------------------------------------------------
+ Server: nginx
+ /: Retrieved x-powered-by header: PHP/8.2
+ 7915 requests: 0 error(s) and 2 item(s) reported on remote host
+ End Time:           2026-08-09 23:01:00
---------------------------------------------------------------------------
"""


def test_parse_nmap_extracts_hosts_and_ports():
    result = parse_nmap(NMAP_XML)
    assert len(result["hosts"]) == 1
    host = result["hosts"][0]
    assert host["address"] == "127.0.0.1"
    assert host["hostname"] == "localhost"
    assert host["state"] == "up"
    assert host["ports"] == [
        {"port": 9000, "protocol": "tcp", "state": "open", "service": "cslistener", "product": "", "version": ""}
    ]


def test_parse_nmap_empty_output():
    assert parse_nmap("") == {"hosts": []}


def test_parse_nmap_blocks_xxe_external_entities():
    result = parse_nmap(NMAP_XML_XXE)
    # defusedxml raises/strips on external entities rather than resolving them;
    # either way, /etc/passwd content must never appear in the parsed output.
    assert "root:" not in str(result)


def test_parse_whatweb_extracts_results():
    result = parse_whatweb(WHATWEB_JSON)
    assert len(result["results"]) == 1
    assert result["results"][0]["target"] == "http://10.0.0.1"
    assert result["results"][0]["plugins"]["HTTPServer"]["string"] == ["nginx"]


def test_parse_nikto_extracts_findings_and_metadata():
    result = parse_nikto(NIKTO_TXT)
    assert result["target_ip"] == "10.0.0.1"
    assert result["target_hostname"] == "10.0.0.1"
    assert "Server: nginx" in result["findings"]
    assert any("x-powered-by" in f for f in result["findings"])
    # metadata / summary lines must not leak into findings
    assert not any(f.startswith("Target") for f in result["findings"])
    assert not any(f.startswith("7915 requests") for f in result["findings"])
