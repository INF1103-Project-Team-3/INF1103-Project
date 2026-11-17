import pytest

from managers.logic_manager.keyword_matcher import KeywordMatcher


@pytest.mark.parametrize("text, word, expected", [
    ("The WIFI drops in lectures.", "wifi", True),         # any case
    ("Wi-Fi is slow.", "wi-fi", True),                      # punctuation inside the word
    ("It is all too much lately.", "too much", True),       # a phrase
    ("Free wifiplus vouchers ran out.", "wifi", False),    # not inside another word
    ("My groupmates never reply.", "group", False),
    ("", "wifi", False),
])
def test_mentions_matches_whole_words_and_phrases_in_any_case(text, word, expected):
    assert KeywordMatcher.mentions(text, word) is expected
