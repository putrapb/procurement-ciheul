import re

from services.numbering import next_number


def test_number_format_and_increment(db):
    first, second = next_number("PR"), next_number("PR")
    assert re.fullmatch(r"PR-\d{6}-0001", first)
    assert second.endswith("-0002")


def test_prefix_sequences_are_independent(db):
    next_number("PR")
    assert next_number("PO").endswith("-0001")
