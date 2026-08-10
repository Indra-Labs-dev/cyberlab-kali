from app.models.target import AuthorizationStatus, Target, TargetType
from app.targets.authorization import infer_default_authorization, is_executable


def test_infer_local_from_127_0_0_1():
    assert infer_default_authorization(None, "127.0.0.1", None) == AuthorizationStatus.LOCAL


def test_infer_local_from_localhost_hostname():
    assert infer_default_authorization("localhost", None, None) == AuthorizationStatus.LOCAL


def test_infer_lab_from_cyberlab_lab_container():
    assert infer_default_authorization("cyberlab-lab-dvwa-abcd1234", None, None) == AuthorizationStatus.LAB


def test_infer_lab_from_cyberlab_kali_container():
    assert infer_default_authorization("cyberlab-kali", None, None) == AuthorizationStatus.LAB


def test_infer_lab_from_url_with_lab_hostname():
    assert infer_default_authorization(None, None, "http://cyberlab-lab-dvwa-xyz:80/") == AuthorizationStatus.LAB


def test_infer_unknown_for_arbitrary_external_host():
    assert infer_default_authorization("scanme.nmap.org", None, None) == AuthorizationStatus.UNKNOWN


def test_infer_unknown_for_arbitrary_ip():
    assert infer_default_authorization(None, "8.8.8.8", None) == AuthorizationStatus.UNKNOWN


def test_is_executable_true_for_lab_authorized_local():
    for status in (AuthorizationStatus.LAB, AuthorizationStatus.AUTHORIZED, AuthorizationStatus.LOCAL):
        target = Target(name="t", target_type=TargetType.IP, authorization_status=status)
        assert is_executable(target) is True


def test_is_executable_false_for_unknown():
    target = Target(name="t", target_type=TargetType.IP, authorization_status=AuthorizationStatus.UNKNOWN)
    assert is_executable(target) is False
