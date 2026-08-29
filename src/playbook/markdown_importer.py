"""
Markdown importer for batch importing knowledge into playbooks.

Parses markdown files and extracts sections as separate bullets,
supporting frontmatter metadata and ADR-style documents.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ParsedBullet:
    """A bullet extracted from markdown."""
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    type: str = 'pattern'
    created_by_model: str = 'human'
    source_file: str | None = None


class MarkdownImporter:
    """
    Import knowledge from markdown files into playbook bullets.
    
    Supports:
    - ## headings as separate bullets
    - YAML frontmatter for tags/type metadata
    - ADR-style documents (Status/Context/Decision/Consequences)
    """

    def __init__(self):
        self._frontmatter_pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
        self._heading_pattern = re.compile(r'^##\s+(.+)$', re.MULTILINE)

    def parse(self, markdown_content: str, source_file: str | None = None) -> list[dict]:
        """
        Parse markdown content into bullet dictionaries.
        
        Args:
            markdown_content: Raw markdown text
            source_file: Optional source filename for metadata
            
        Returns:
            List of bullet dictionaries with title, content, tags, type, etc.
        """
        # Extract frontmatter if present
        frontmatter = {}
        content = markdown_content

        fm_match = self._frontmatter_pattern.match(content)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1)) or {}
            except yaml.YAMLError:
                frontmatter = {}
            content = content[fm_match.end():]

        # Parse frontmatter tags
        global_tags = []
        if 'tags' in frontmatter:
            tags_value = frontmatter['tags']
            if isinstance(tags_value, str):
                global_tags = [t.strip() for t in tags_value.split(',')]
            elif isinstance(tags_value, list):
                global_tags = tags_value

        global_type = frontmatter.get('type')  # None if not set

        # Split by ## headings
        bullets = []
        sections = self._split_by_headings(content)

        for title, section_content in sections:
            bullet = {
                'title': title,
                'content': section_content.strip(),
                'tags': global_tags.copy(),
                'created_by_model': 'human',
            }
            if global_type:
                bullet['type'] = global_type
            if source_file:
                bullet['source_file'] = source_file
            bullets.append(bullet)

        return bullets

    def _split_by_headings(self, content: str) -> list[tuple[str, str]]:
        """Split content by ## headings, returning (title, content) pairs."""
        sections = []

        # Find all ## headings
        heading_matches = list(self._heading_pattern.finditer(content))

        if not heading_matches:
            return sections

        for i, match in enumerate(heading_matches):
            title = match.group(1).strip()
            start = match.end()

            # Content goes until next heading or end of file
            if i + 1 < len(heading_matches):
                end = heading_matches[i + 1].start()
            else:
                end = len(content)

            section_content = content[start:end]
            sections.append((title, section_content))

        return sections

    def parse_file(self, file_path: Path | str) -> list[dict]:
        """
        Parse a markdown file into bullets.
        
        Args:
            file_path: Path to the markdown file
            
        Returns:
            List of bullet dictionaries
        """
        path = Path(file_path)
        content = path.read_text()
        return self.parse(content, source_file=path.name)
