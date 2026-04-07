"""Tests for MarkdownImporter."""
import pytest
from src.playbook.markdown_importer import MarkdownImporter


class TestMarkdownImporter:
    """Tests for MarkdownImporter class."""

    def test_can_be_created(self):
        """MarkdownImporter can be instantiated."""
        importer = MarkdownImporter()
        assert importer is not None

    def test_parses_h2_sections_into_bullets(self):
        """Each ## heading becomes a separate bullet."""
        importer = MarkdownImporter()
        markdown = """
## Decision: Use PostgreSQL
We chose PostgreSQL for its reliability.

## Decision: Use Redis for caching  
Redis provides fast in-memory caching.
"""
        bullets = importer.parse(markdown)
        
        assert len(bullets) == 2
        assert bullets[0]['title'] == 'Decision: Use PostgreSQL'
        assert 'PostgreSQL' in bullets[0]['content']
        assert bullets[1]['title'] == 'Decision: Use Redis for caching'

    def test_extracts_frontmatter_tags(self):
        """Tags are extracted from YAML frontmatter."""
        importer = MarkdownImporter()
        markdown = """---
tags: architecture, database
type: decision
---
## Use PostgreSQL
Content here.
"""
        bullets = importer.parse(markdown)
        
        assert bullets[0]['tags'] == ['architecture', 'database']
        assert bullets[0]['type'] == 'decision'

    def test_handles_adr_format(self):
        """ADR format with Status/Context/Decision/Consequences is preserved."""
        importer = MarkdownImporter()
        markdown = """
## ADR-001: Use PostgreSQL

**Status:** Accepted

**Context:** We need a reliable database.

**Decision:** Use PostgreSQL.

**Consequences:** Need to manage PostgreSQL infrastructure.
"""
        bullets = importer.parse(markdown)
        
        assert len(bullets) == 1
        assert bullets[0]['title'] == 'ADR-001: Use PostgreSQL'
        assert 'Status' in bullets[0]['content']
        assert 'Decision' in bullets[0]['content']

    def test_sets_human_authored_metadata(self):
        """Imported bullets are marked as human-authored."""
        importer = MarkdownImporter()
        markdown = """
## Some Decision
Content.
"""
        bullets = importer.parse(markdown, source_file='decisions.md')
        
        assert bullets[0]['created_by_model'] == 'human'
        assert bullets[0]['source_file'] == 'decisions.md'


class TestLearnFromFile:
    """Tests for learn_from_file CLI function."""

    def test_imports_markdown_sections_to_playbook(self, tmp_path):
        """Markdown sections are imported as playbook bullets."""
        from unittest.mock import Mock, MagicMock
        from src.playbook.learn_cli import learn_from_file
        
        # Create test markdown file
        md_file = tmp_path / "decisions.md"
        md_file.write_text("""
## Use PostgreSQL
We chose PostgreSQL for reliability.

## Use Redis
Redis for caching.
""")
        
        # Mock manager
        manager = Mock()
        manager.add_bullet = MagicMock(side_effect=lambda pid, data: Mock(id=f"bullet-{data.content[:10]}"))
        
        bullets = learn_from_file(
            manager=manager,
            playbook_id="test-playbook",
            file_path=md_file,
        )
        
        assert len(bullets) == 2
        assert manager.add_bullet.call_count == 2

    def test_applies_cli_tags_to_all_bullets(self, tmp_path):
        """CLI --tags are applied to all imported bullets."""
        from unittest.mock import Mock, MagicMock
        from src.playbook.learn_cli import learn_from_file
        
        md_file = tmp_path / "notes.md"
        md_file.write_text("""
## Note 1
Content 1.
""")
        
        manager = Mock()
        captured_data = []
        def capture_add(pid, data):
            captured_data.append(data)
            return Mock(id="bullet-1")
        manager.add_bullet = capture_add
        
        learn_from_file(
            manager=manager,
            playbook_id="test",
            file_path=md_file,
            tags=["review", "backend"],
        )
        
        assert "review" in captured_data[0].tags
        assert "backend" in captured_data[0].tags

    def test_uses_type_from_cli_argument(self, tmp_path):
        """CLI --type sets the bullet section."""
        from unittest.mock import Mock
        from src.playbook.learn_cli import learn_from_file
        
        md_file = tmp_path / "decisions.md"
        md_file.write_text("""
## Decision 1
Content.
""")
        
        manager = Mock()
        captured_data = []
        def capture_add(pid, data):
            captured_data.append(data)
            return Mock(id="bullet-1")
        manager.add_bullet = capture_add
        
        learn_from_file(
            manager=manager,
            playbook_id="test",
            file_path=md_file,
            bullet_type="decision",
        )
        
        assert captured_data[0].section == "decision"

    def test_raises_error_for_missing_file(self):
        """FileNotFoundError raised for missing files."""
        from unittest.mock import Mock
        from src.playbook.learn_cli import learn_from_file
        import pytest
        
        manager = Mock()
        
        with pytest.raises(FileNotFoundError):
            learn_from_file(
                manager=manager,
                playbook_id="test",
                file_path="/nonexistent/file.md",
            )
