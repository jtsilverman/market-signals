from market_signals.poller import extract_keywords


class TestExtractKeywords:
    def test_normal_text(self):
        stopwords = {"the", "will", "to", "of", "in"}
        result = extract_keywords("Bitcoin Will Crash to New Lows in 2026", stopwords)
        # "will", "to", "in" are stopwords; "new" is 3 chars so included
        assert "bitcoin" in result
        assert "crash" in result
        assert "lows" in result
        assert "new" in result
        assert "will" not in result
        assert "to" not in result
        assert "in" not in result

    def test_only_stopwords(self):
        stopwords = {"the", "is", "and", "for"}
        result = extract_keywords("the is and for", stopwords)
        assert result == []

    def test_empty_string(self):
        result = extract_keywords("", {"the", "is"})
        assert result == []

    def test_short_words_filtered(self):
        """Words with 2 or fewer characters are excluded."""
        result = extract_keywords("I am ok no go do it", set())
        # "am", "ok", "no", "go", "do", "it" are 2 chars -> excluded. "I" is 1 char -> excluded.
        assert result == []

    def test_exactly_three_chars(self):
        """Words with exactly 3 characters pass the filter."""
        result = extract_keywords("the big cat ran far", set())
        assert "the" in result
        assert "big" in result
        assert "cat" in result
        assert "ran" in result
        assert "far" in result

    def test_non_alpha_stripped(self):
        """Only alphabetic sequences are extracted."""
        result = extract_keywords("bitcoin's price: $50,000!", set())
        assert "bitcoin" in result
        assert "price" in result
        # Numbers and punctuation are not included
        assert "50" not in result
        assert "000" not in result

    def test_case_insensitive(self):
        result = extract_keywords("BITCOIN Price CRASH", set())
        assert all(w == w.lower() for w in result)
        assert "bitcoin" in result
        assert "price" in result
        assert "crash" in result
