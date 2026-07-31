from __future__ import annotations

from w_mwxt_wavetable_tool.identity import IdentityReply


def test_users_xt_identity_reply() -> None:
    raw = bytes.fromhex("F0 7E 06 02 3E 0E 00 03 00 32 2E 33 33 F7")
    reply = IdentityReply.from_bytes(raw)
    assert reply.family_code == 0x000E
    assert reply.member_code == 0x0003
    assert reply.version == "2.33"
    assert reply.is_xt_10_voice_non_expandable
