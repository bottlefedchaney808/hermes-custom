import pytest

from brain_rag.redact import MASK, redact


def test_luhn_valid_card_numbers_are_masked():
    assert redact("card 4111 1111 1111 1111 exp") == f"card {MASK} exp"
    assert redact("4111-1111-1111-1111") == MASK


def test_ordinary_numbers_survive():
    for text in ("order 1234567890123", "wall area 45,210 SF", "job 2026-09-25", "rev 3 of 12, 2026-10-14"):
        assert redact(text) == text


def test_api_keys_and_tokens_are_masked():
    for secret in ("sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv", "AIzaSyA1234567890abcdefghijklmnopqrstu",
                   "ghp_0123456789abcdefghijklmnopqrstuvwxyz", "Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijk"):
        assert secret not in redact(f"use {secret} here")


def test_assignments_keep_the_key_name_and_mask_the_value():
    assert redact("password: hunter2") == f"password: {MASK}"
    assert redact('API_KEY="abc123"') == f"API_KEY={MASK}"


def test_private_key_blocks_are_masked():
    block = "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----"
    assert redact(f"x {block} y") == f"x {MASK} y"


def test_uuid_shaped_key_on_a_key_line_is_masked():
    assert redact("01a09d2d-4e4e-771a-b937-4e63d05b0574 api key") == f"{MASK} api key"
    assert redact("kalshi key id: 01a09d2d-4e4e-771a-b937-4e63d05b0574") == f"kalshi key id: {MASK}"


def test_uuids_without_key_context_survive():
    text = "session 01a09d2d-4e4e-771a-b937-4e63d05b0574 ended"
    assert redact(text) == text


def test_long_token_on_a_token_line_is_masked_but_prose_is_not():
    assert "abc123DEF456ghi789JKL012mno" not in redact("token abc123DEF456ghi789JKL012mno")
    assert redact("the token budget is fine") == "the token budget is fine"


def test_business_emails_are_masked():
    for email in ("jane.doe@vendor-example.com", "bids@gc-example.co", "a+tag@sub.example.org"):
        out = redact(f"contact {email} for the quote")
        assert email not in out
        assert out == f"contact {MASK} for the quote"


def test_a_single_domain_is_not_special_cased():
    # The owner, a teammate and a client can all write from one company domain,
    # so no domain is exempt: every non-technical address is masked.
    for addr in ("owner@company-example.com", "teammate@company-example.com", "client@company-example.com"):
        assert redact(f"from {addr} today") == f"from {MASK} today"


def test_technical_addresses_survive():
    for text in (
        "ssh admin@100.64.0.1",
        "deploy@10.0.0.7 is the worker",
        "POST https://api.x.ai/v1 with sa@proj.iam.gserviceaccount.com",
        "svc@system.gserviceaccount.com",
        "host user@inference-api.nousresearch.com",
    ):
        assert redact(text) == text


def test_email_lookalikes_that_are_not_addresses_survive():
    for text in ("the @mention in a thread", "decorator @cache.clear", "price @ 5 each"):
        assert redact(text) == text


@pytest.mark.parametrize(
    "phone",
    ["(555) 010-0199", "555-010-0199", "555.010.0199", "555 010 0199", "+1 555-010-0199", "1-555-010-0199"],
)
def test_phone_numbers_are_masked(phone):
    out = redact(f"call {phone} now")
    assert phone not in out
    assert MASK in out
    assert out.startswith("call ") and out.endswith(" now")


def test_numbers_that_look_phone_like_but_are_not_survive():
    for text in ("version 10.20.30", "ip 192.168.100.200", "pid 4242424242 ended", "SF 1,234,567", "rows 123-45-6789x"):
        assert redact(text) == text
