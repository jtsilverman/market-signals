from market_signals.correlator import compute_correlation_score


class TestComputeCorrelationScore:
    def test_empty_market_keywords(self):
        assert compute_correlation_score([], ["bitcoin", "price"], 0) == 0.0

    def test_empty_article_keywords(self):
        assert compute_correlation_score(["bitcoin", "price"], [], 0) == 0.0

    def test_both_empty(self):
        assert compute_correlation_score([], [], 0) == 0.0

    def test_one_empty_set_market(self):
        """Edge: market keywords empty, article has words."""
        assert compute_correlation_score([], ["election", "polls"], 100) == 0.0

    def test_one_empty_set_article(self):
        """Edge: article keywords empty, market has words."""
        assert compute_correlation_score(["election", "polls"], [], 100) == 0.0

    def test_full_overlap_zero_time(self):
        keywords = ["bitcoin", "price", "crash"]
        score = compute_correlation_score(keywords, keywords, 0)
        assert score == 1.0

    def test_full_overlap_nonzero_time(self):
        keywords = ["bitcoin", "price"]
        # 3600s = half of 7200 default window -> time_factor = 0.5
        score = compute_correlation_score(keywords, keywords, 3600)
        assert score == 0.5

    def test_partial_overlap(self):
        market = ["bitcoin", "price", "crash", "today"]
        article = ["bitcoin", "crash", "analysis"]
        # overlap = {bitcoin, crash} -> 2/4 = 0.5, time_diff=0 -> factor=1.0
        score = compute_correlation_score(market, article, 0)
        assert score == 0.5

    def test_no_overlap(self):
        score = compute_correlation_score(["bitcoin"], ["election"], 0)
        assert score == 0.0

    def test_large_time_diff_at_max(self):
        """Time diff exactly at max_time_window -> time_factor = 0."""
        score = compute_correlation_score(["bitcoin"], ["bitcoin"], 7200)
        assert score == 0.0

    def test_large_time_diff_beyond_max(self):
        """Time diff beyond max window -> time_factor clamped to 0."""
        score = compute_correlation_score(["bitcoin"], ["bitcoin"], 10000)
        assert score == 0.0

    def test_negative_time_diff(self):
        """Absolute value is used, so negative time_diff works the same."""
        pos = compute_correlation_score(["bitcoin"], ["bitcoin"], 1800)
        neg = compute_correlation_score(["bitcoin"], ["bitcoin"], -1800)
        assert pos == neg

    def test_custom_max_time_window(self):
        # max_time_window=3600, time_diff=1800 -> factor=0.5
        score = compute_correlation_score(
            ["bitcoin"], ["bitcoin"], 1800, max_time_window=3600
        )
        assert score == 0.5

    def test_rounding(self):
        """Score is rounded to 3 decimal places."""
        # 1/3 overlap * (1 - 1000/7200) time factor
        market = ["aaa", "bbb", "ccc"]
        article = ["aaa"]
        score = compute_correlation_score(market, article, 1000)
        assert score == round((1 / 3) * (1 - 1000 / 7200), 3)
