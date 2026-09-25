from brain_rag.redact import MASK, redact


def test_luhn_valid_card_numbers_are_masked():
    assert redact("card 4111 1111 1111 1111 exp") == f"card {MASK} exp"
    assert redact("4111-1111-1111-1111") == MASK


def test_ordinary_numbers_survive():
    for text in ("order 1234567890123", "wall area 45,210 SF", "call (501) 891-0263", "job 2026-09-25"):
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
