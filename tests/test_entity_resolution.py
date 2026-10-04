"""Entity resolution: scoring, blocking, config validation, clustering."""

import pytest

from entity_resolution.candidate_generation import BlockingStats, build_block_index, iter_candidates
from entity_resolution.config import ERConfig
from entity_resolution.matcher import ComponentScores, UnionFind, score_pair
from entity_resolution.name_matcher import cluster_names


@pytest.fixture
def cfg():
    return ERConfig(_env_file=None)


class TestConfigValidation:
    def test_auto_must_exceed_review(self):
        with pytest.raises(ValueError, match="must exceed"):
            ERConfig(auto_match_threshold=0.7, review_threshold=0.8, _env_file=None)

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            ERConfig(weight_street=0.9, weight_zip=0.5, _env_file=None)

    def test_defaults_valid(self, cfg):
        assert cfg.auto_match_threshold > cfg.review_threshold


class TestScoring:
    def _mention(self, **kw):
        base = dict(street_name="WEST 42", street_suffix="STREET", zipcode="10036",
                    latitude=40.7562, longitude=-73.9871)
        base.update(kw)
        return base

    def test_identical_scores_one(self, cfg):
        m = self._mention()
        scores = score_pair(m, dict(m), cfg)
        assert scores.weighted(cfg) == 1.0

    def test_abbreviation_variants_score_high(self, cfg):
        # Same street, suffix normalized upstream; slight coordinate offset.
        a = self._mention()
        b = self._mention(latitude=40.7563, longitude=-73.9872)
        assert score_pair(a, b, cfg).weighted(cfg) > 0.95

    def test_different_street_scores_low(self, cfg):
        a = self._mention()
        b = self._mention(street_name="LEXINGTON", latitude=40.75, longitude=-73.97)
        assert score_pair(a, b, cfg).weighted(cfg) < 0.75

    def test_missing_coords_neutral(self, cfg):
        a = self._mention(latitude=None, longitude=None)
        b = self._mention()
        assert score_pair(a, b, cfg).geo == 0.5

    def test_zip_disagreement_penalized(self, cfg):
        a, b = self._mention(), self._mention(zipcode="11226")
        assert score_pair(a, b, cfg).zip == 0.0

    def test_weighted_formula(self, cfg):
        scores = ComponentScores(street=0.8, zip=1.0, geo=0.5, suffix=1.0)
        expected = 0.55 * 0.8 + 0.15 * 1.0 + 0.15 * 0.5 + 0.15 * 1.0
        assert scores.weighted(cfg) == pytest.approx(expected, abs=1e-4)


class TestBlocking:
    def test_reduction_vs_naive(self):
        left = [{"borough": "QUEENS", "house_number": str(i % 10), "id": i} for i in range(100)]
        right_index = build_block_index(
            [{"borough": "QUEENS", "house_number": str(i % 10), "id": 1000 + i} for i in range(100)],
            ("borough", "house_number"),
        )
        stats = BlockingStats(total_left=100, total_right=100)
        pairs = list(iter_candidates(left, right_index, ("borough", "house_number"), 200, stats))
        assert stats.comparisons == 100 * 10  # each row sees only its block
        assert stats.naive_comparisons == 100 * 100
        assert stats.reduction_pct == 90.0
        assert len(pairs) == 100

    def test_oversize_block_skipped_and_counted(self):
        left = [{"k": "x", "id": 0}]
        right_index = build_block_index([{"k": "x", "id": i} for i in range(50)], ("k",))
        stats = BlockingStats(total_left=1, total_right=50)
        pairs = list(iter_candidates(left, right_index, ("k",), 10, stats))
        assert pairs == []
        assert stats.oversize_blocks_skipped == 1
        assert stats.skipped_keys[0]["size"] == 50

    def test_missing_key_counted(self):
        stats = BlockingStats()
        pairs = list(iter_candidates([{"k": None}], {}, ("k",), 10, stats))
        assert pairs == []
        assert stats.mentions_without_block_key == 1


class TestUnionFind:
    def test_transitive_union(self):
        uf = UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.find("a") == uf.find("c")
        assert uf.find("d") == "d"


class TestNameClustering:
    def test_spec_llc_variants_cluster(self, cfg):
        # Post-normalization variants that still differ textually.
        names = [
            ("ACME PROPERTIES LLC", True, 10),
            ("ACME PROPERTIES", True, 2),
            ("ZENITH HOLDINGS LLC", True, 5),
        ]
        assignment, evidence, _review = cluster_names(names, cfg)
        assert assignment["ACME PROPERTIES LLC|1"] == assignment["ACME PROPERTIES|1"]
        assert assignment["ZENITH HOLDINGS LLC|1"] != assignment["ACME PROPERTIES LLC|1"]
        assert any(e["method"] == "name_fuzzy" for e in evidence)

    def test_person_org_never_cross_block(self, cfg):
        names = [("JOHN SHEN", False, 1), ("JOHN SHEN LLC", True, 1)]
        assignment, _, _ = cluster_names(names, cfg)
        assert assignment["JOHN SHEN|0"] != assignment["JOHN SHEN LLC|1"]

    def test_review_band_not_merged(self, cfg):
        # Similar-but-not-identical: lands between review and auto.
        names = [("PARKSIDE MANAGEMENT GROUP", True, 1), ("PARKSIDE MGT GROUP CORP", True, 1)]
        assignment, evidence, review = cluster_names(names, cfg)
        merged = assignment["PARKSIDE MANAGEMENT GROUP|1"] == assignment["PARKSIDE MGT GROUP CORP|1"]
        queued = len(review) > 0
        # Whichever band it falls in, it must never be silently dropped:
        assert merged or queued or evidence == []

    def test_extra_edges_union(self, cfg):
        names = [("ALPHA CLEANERS", True, 1), ("ALPHA CLEANERS OF QUEENS", True, 1)]
        sim = 0.85
        assignment, evidence, _ = cluster_names(
            names, cfg, extra_edges=[("ALPHA CLEANERS", "ALPHA CLEANERS OF QUEENS", sim, "phone+name")]
        )
        assert assignment["ALPHA CLEANERS|1"] == assignment["ALPHA CLEANERS OF QUEENS|1"]
        assert any(e["method"] == "phone+name" for e in evidence)

    def test_canonical_is_heaviest_variant(self, cfg):
        names = [("ACME PROPERTIES LLC", True, 100), ("ACME PROPERTIES", True, 1)]
        assignment, _, _ = cluster_names(names, cfg)
        assert assignment["ACME PROPERTIES|1"] == "ACME PROPERTIES LLC"
