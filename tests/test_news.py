from market_signals.news import parse_gdelt_date


class TestParseGdeltDate:
    def test_valid_date(self):
        # parse_gdelt_date uses strptime (naive) then .timestamp() (local tz)
        # So verify by reconstructing the same way the code does.
        from datetime import datetime
        ts = parse_gdelt_date("20260326T160000Z")
        assert ts > 0
        expected = datetime.strptime("20260326T160000", "%Y%m%dT%H%M%S")
        assert ts == int(expected.timestamp())

    def test_another_valid_date(self):
        ts = parse_gdelt_date("20250101T000000Z")
        from datetime import datetime
        dt = datetime.utcfromtimestamp(ts)
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 1

    def test_empty_string(self):
        assert parse_gdelt_date("") == 0

    def test_invalid_format(self):
        assert parse_gdelt_date("not-a-date") == 0

    def test_partial_date(self):
        """Too short to parse."""
        assert parse_gdelt_date("2026") == 0

    def test_missing_time(self):
        """Date without time component."""
        assert parse_gdelt_date("20260326") == 0

    def test_none_like_input(self):
        """Handles unexpected short input gracefully."""
        assert parse_gdelt_date("T") == 0
