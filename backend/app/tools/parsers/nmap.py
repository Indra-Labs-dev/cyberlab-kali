from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_nmap(raw_output: str) -> dict:
    if not raw_output.strip():
        return {"hosts": []}

    try:
        root = ET.fromstring(raw_output)
    except (ET.ParseError, DefusedXmlException):
        return {"hosts": [], "parse_error": True}

    hosts = []
    for host_el in root.findall("host"):
        state_el = host_el.find("status")
        address_el = host_el.find("address")
        hostname_el = host_el.find("hostnames/hostname")

        ports = []
        for port_el in host_el.findall("ports/port"):
            state = port_el.find("state")
            service = port_el.find("service")
            ports.append(
                {
                    "port": int(port_el.get("portid", 0)),
                    "protocol": port_el.get("protocol", ""),
                    "state": state.get("state") if state is not None else "unknown",
                    "service": service.get("name") if service is not None else None,
                    "product": service.get("product") if service is not None else None,
                    "version": service.get("version") if service is not None else None,
                }
            )

        hosts.append(
            {
                "address": address_el.get("addr") if address_el is not None else None,
                "hostname": hostname_el.get("name") if hostname_el is not None else None,
                "state": state_el.get("state") if state_el is not None else "unknown",
                "ports": ports,
            }
        )

    return {"hosts": hosts}
