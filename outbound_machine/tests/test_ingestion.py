"""Tests for candidate ingestion and domain normalisation."""
import pytest
import csv
import tempfile
from pathlib import Path

from app.schemas.candidate import CandidateIn, CandidateRow


class TestCandidateSchema:
    def test_domain_normalised(self):
        c = CandidateIn(brand_name="Test Brand", domain="https://www.example.com/")
        assert c.domain == "example.com"

    def test_brand_name_stripped(self):
        c = CandidateIn(brand_name="  Test Brand  ", domain="example.com")
        assert c.brand_name == "Test Brand"

    def test_vertical_lowercased(self):
        c = CandidateIn(brand_name="Brand", domain="x.com", vertical="Apparel")
        assert c.vertical == "apparel"

    def test_optional_fields_default_none(self):
        c = CandidateIn(brand_name="Brand", domain="brand.com")
        assert c.source is None
        assert c.vertical is None
        assert c.notes is None


class TestIngestionService:
    def _make_csv(self, rows: list[dict]) -> Path:
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        if rows:
            writer = csv.DictWriter(tf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        tf.close()
        return Path(tf.name)

    def test_ingest_from_csv(self):
        from unittest.mock import MagicMock
        from app.services.ingestion.ingestion_service import ingest_csv
        from app.db.models import Candidate, Lead

        rows = [
            {"brand_name": "Brand A", "domain": "branda.com", "vertical": "apparel"},
            {"brand_name": "Brand B", "domain": "brandb.com", "vertical": "beauty"},
        ]
        csv_path = self._make_csv(rows)

        # Mock session
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        session.flush = MagicMock()
        session.commit = MagicMock()

        stats = ingest_csv(csv_path, session)

        assert stats["ingested"] == 2
        assert stats["errors"] == 0
        assert stats["skipped_duplicate"] == 0

        csv_path.unlink()  # cleanup

    def test_deduplication_in_csv(self):
        from unittest.mock import MagicMock
        from app.services.ingestion.ingestion_service import ingest_csv

        rows = [
            {"brand_name": "Brand A", "domain": "branda.com"},
            {"brand_name": "Brand A Dupe", "domain": "https://www.branda.com/"},  # same domain
        ]
        csv_path = self._make_csv(rows)

        call_count = [0]
        def mock_first():
            call_count[0] += 1
            # First call: not exists, second: exists
            if call_count[0] == 1:
                return None
            return MagicMock()  # existing record

        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = mock_first
        session.flush = MagicMock()
        session.commit = MagicMock()

        stats = ingest_csv(csv_path, session)

        assert stats["ingested"] == 1
        assert stats["skipped_duplicate"] == 1

        csv_path.unlink()

    def test_missing_domain_column_raises(self):
        from unittest.mock import MagicMock
        from app.services.ingestion.ingestion_service import ingest_csv

        rows = [{"brand_name": "Brand", "source": "manual"}]
        csv_path = self._make_csv(rows)

        session = MagicMock()
        with pytest.raises(ValueError, match="domain"):
            ingest_csv(csv_path, session)

        csv_path.unlink()
