from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException


def parse_sslscan(raw_output: str) -> dict:
    if not raw_output.strip():
        return {"targets": []}

    try:
        root = ET.fromstring(raw_output)
    except (ET.ParseError, DefusedXmlException):
        return {"targets": [], "parse_error": True}

    targets = []
    for test_el in root.findall("ssltest"):
        protocols = [
            {"version": p.get("version"), "enabled": p.get("enabled") == "1"} for p in test_el.findall("protocol")
        ]
        accepted_ciphers = [
            {"cipher": c.get("cipher"), "bits": c.get("bits"), "protocol": c.get("sslversion")}
            for c in test_el.findall("cipher")
            if c.get("status") == "accepted"
        ]
        cert_el = test_el.find("certificate")
        certificate = None
        if cert_el is not None:
            subject_el = cert_el.find("subject")
            expiry_el = cert_el.find("not-valid-after")
            certificate = {
                "subject": subject_el.text if subject_el is not None else None,
                "not_valid_after": expiry_el.text if expiry_el is not None else None,
            }
        targets.append(
            {
                "host": test_el.get("host"),
                "port": test_el.get("port"),
                "protocols": protocols,
                "accepted_ciphers": accepted_ciphers,
                "certificate": certificate,
            }
        )
    return {"targets": targets}
