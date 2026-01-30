"""Tests for the full pipeline"""

import pytest
import json
from pathlib import Path

from app.services.pipeline import NameDetectionPipeline
from app.models.schemas import NameCategory


@pytest.fixture
def pipeline():
    """Create pipeline instance (without loading heavy models for unit tests)"""
    p = NameDetectionPipeline()
    # Don't initialize full pipeline in unit tests
    return p


@pytest.fixture
def test_data():
    """Load test data"""
    test_file = Path(__file__).parent / "test_data" / "comments.json"
    with open(test_file, "r", encoding="utf-8") as f:
        return json.load(f)


class TestPipelineNoNameDetection:
    """Test no-name detection through the pipeline"""

    def test_empty_comment(self, pipeline):
        result = pipeline.process_sync("")
        assert result.has_name is False
        assert result.category == NameCategory.NO_NAME

    def test_salary_comment(self, pipeline):
        result = pipeline.process_sync("Зарплата за грудень")
        assert result.has_name is False
        assert result.tier_used == 1  # Should be handled by quick filter

    def test_numeric_comment(self, pipeline):
        result = pipeline.process_sync("1000 грн")
        assert result.has_name is False
        assert result.tier_used == 1


class TestPipelineCaching:
    """Test caching functionality"""

    def test_cache_hit(self, pipeline):
        comment = "Зарплата за грудень"

        # First call
        result1 = pipeline.process_sync(comment)
        stats1 = pipeline.get_stats()

        # Second call - should hit cache
        result2 = pipeline.process_sync(comment)
        stats2 = pipeline.get_stats()

        assert result1.has_name == result2.has_name
        assert result1.category == result2.category
        assert stats2["cache_hits"] > stats1["cache_hits"]


class TestPipelineStats:
    """Test statistics tracking"""

    def test_stats_increment(self, pipeline):
        initial_stats = pipeline.get_stats()
        initial_total = initial_stats["total_requests"]

        pipeline.process_sync("Тестовий коментар")

        final_stats = pipeline.get_stats()
        assert final_stats["total_requests"] == initial_total + 1


class TestPipelineWithTestData:
    """Integration tests with test data file"""

    def test_no_name_comments(self, pipeline, test_data):
        """Test all no-name comments from test data"""
        for item in test_data["no_name_comments"]:
            result = pipeline.process_sync(item["comment"])
            assert result.has_name == item["expected_has_name"], \
                f"Failed for: {item['comment']}"

    def test_edge_cases(self, pipeline, test_data):
        """Test edge cases"""
        for item in test_data["edge_cases"]:
            result = pipeline.process_sync(item["comment"])
            assert result.has_name == item["expected_has_name"], \
                f"Failed for: '{item['comment']}'"
