"""client_key: cf-connecting-ip is only trusted when the connection comes from the local tunnel."""
from types import SimpleNamespace

from app.security import client_key


def c(host): return SimpleNamespace(host=host)


def test_tunnel_connection_uses_the_forwarded_client_ip():
    assert client_key({"cf-connecting-ip": "203.0.113.7"}, c("127.0.0.1")) == "203.0.113.7"
    assert client_key({"cf-connecting-ip": "203.0.113.7"}, c("::1")) == "203.0.113.7"


def test_direct_connection_cannot_fake_its_ip():
    assert client_key({"cf-connecting-ip": "203.0.113.7"}, c("192.168.1.50")) == "192.168.1.50"
    assert client_key({"cf-connecting-ip": "1.2.3.4"}, c("198.51.100.9")) == "198.51.100.9"


def test_missing_header_or_client_falls_back():
    assert client_key({}, c("127.0.0.1")) == "127.0.0.1"
    assert client_key({"cf-connecting-ip": "  "}, c("127.0.0.1")) == "127.0.0.1"
    assert client_key({}, None) == "unknown"


def test_forwarded_value_is_length_limited():
    assert len(client_key({"cf-connecting-ip": "x" * 500}, c("127.0.0.1"))) == 64
