from django.test import RequestFactory

from helpers.http import get_client_ip


def test_get_client_ip_prefers_x_forwarded_for():
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="203.0.113.5, 10.0.0.1")

    assert get_client_ip(request) == "203.0.113.5"


def test_get_client_ip_falls_back_to_remote_addr():
    request = RequestFactory().get("/", REMOTE_ADDR="127.0.0.1")

    assert get_client_ip(request) == "127.0.0.1"
