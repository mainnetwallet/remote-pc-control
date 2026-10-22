from tools.wol_sender import make_packet
import pytest

def test_packet_format():
    p=make_packet("AA:BB:CC:DD:EE:FF"); assert len(p)==102 and p[:6]==b"\xff"*6
    assert p[6:]==bytes.fromhex("AABBCCDDEEFF")*16

def test_bad_mac():
    with pytest.raises(ValueError): make_packet("not-a-mac")
