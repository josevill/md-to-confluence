"""Markdown to Confluence XHTML converter."""

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

import markdown

# from markdown.extensions import fenced_code
# from markdown.extensions.tables import TableExtension
# from markdown.extensions.toc import TocExtension

logger = logging.getLogger(__name__)


class MarkdownConverter:
    """Converts Markdown content to Confluence storage format."""

    # Confluence macro templates
    CODE_MACRO_TEMPLATE = """<ac:structured-macro ac:name="code">
        <ac:parameter ac:name="language">{language}</ac:parameter>
        <ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>
    </ac:structured-macro>"""

    INFO_MACRO_TEMPLATE = """<ac:structured-macro ac:name="info">
        <ac:rich-text-body>{content}</ac:rich-text-body>
    </ac:structured-macro>"""

    NOTE_MACRO_TEMPLATE = """<ac:structured-macro ac:name="note">
        <ac:rich-text-body>{content}</ac:rich-text-body>
    </ac:structured-macro>"""

    WARNING_MACRO_TEMPLATE = """<ac:structured-macro ac:name="warning">
        <ac:rich-text-body>{content}</ac:rich-text-body>
    </ac:structured-macro>"""

    def __init__(self) -> None:
        """Initialize the Markdown converter with necessary extensions."""
        self.md = markdown.Markdown(
            extensions=[
                "markdown.extensions.fenced_code",
                "markdown.extensions.tables",
                "markdown.extensions.toc",
                "markdown.extensions.attr_list",
                "markdown.extensions.def_list",
                "markdown.extensions.footnotes",
            ]
        )

    def _extract_code_blocks(self: "MarkdownConverter", content: str) -> Tuple[str, dict]:
        """Extract code blocks from content and replace with placeholders.

        Args:
            content: The markdown content

        Returns:
            Tuple containing:
                - Content with code blocks replaced by placeholders
                - Dictionary mapping placeholders to code block info
        """
        code_blocks = {}
        pattern = re.compile(r"```(\w+)?\n(.*?)\n```", re.DOTALL)

        def replace(match):
            language = match.group(1) or "text"
            code = match.group(2)
            placeholder = f"CODE_BLOCK_{len(code_blocks)}"
            code_blocks[placeholder] = (language, code)
            return placeholder

        processed_content = pattern.sub(replace, content)
        return processed_content, code_blocks

    def _process_admonitions(self: "MarkdownConverter", content: str) -> str:
        """Process admonition blocks (info, note, warning).

        Args:
            content: The HTML content

        Returns:
            Content with admonitions converted to Confluence macros
        """
        # Process !!! info blocks
        content = re.sub(
            r'<div class="admonition info">(.*?)</div>',
            lambda m: self.INFO_MACRO_TEMPLATE.format(content=m.group(1)),
            content,
            flags=re.DOTALL,
        )

        # Process !!! note blocks
        content = re.sub(
            r'<div class="admonition note">(.*?)</div>',
            lambda m: self.NOTE_MACRO_TEMPLATE.format(content=m.group(1)),
            content,
            flags=re.DOTALL,
        )

        # Process !!! warning blocks
        content = re.sub(
            r'<div class="admonition warning">(.*?)</div>',
            lambda m: self.WARNING_MACRO_TEMPLATE.format(content=m.group(1)),
            content,
            flags=re.DOTALL,
        )

        return content

    def _restore_code_blocks(self: "MarkdownConverter", content: str, code_blocks: dict) -> str:
        """Restore code blocks from placeholders.

        Args:
            content: Content with code block placeholders
            code_blocks: Dictionary mapping placeholders to code block info

        Returns:
            Content with code blocks restored as Confluence macros
        """
        for placeholder, (language, code) in code_blocks.items():
            macro = self.CODE_MACRO_TEMPLATE.format(language=language, code=code.strip())
            content = content.replace(placeholder, macro)
        return content

    def _process_images(
        self: "MarkdownConverter", content: str, base_path: Optional[Path] = None
    ) -> str:
        """Process image references.

        Args:
            content: The HTML content
            base_path: Base path for resolving relative image paths

        Returns:
            Content with processed image references
        """

        def process_image(match):
            src = match.group(1)
            alt = match.group(2) or ""

            # If we have a base path and the src is relative, make it absolute
            if base_path and not src.startswith(("http://", "https://", "/")):
                image_path = base_path / src
                if image_path.exists():
                    src = str(image_path.resolve())

            return f"<img src={src!r} alt={alt!r}/>"

        image_pattern = r'<img src="([^"]+)"(?:\s+alt="([^"]*)")?[^>]*>'
        return re.sub(image_pattern, process_image, content)

    def convert(self: "MarkdownConverter", content: str, base_path: Optional[Path] = None) -> str:
        """Convert Markdown content to Confluence storage format.

        Args:
            content: The markdown content to convert
            base_path: Optional base path for resolving relative paths

        Returns:
            The converted content in Confluence storage format
        """
        logger.info("Converting markdown content to Confluence format")

        # Extract code blocks before markdown conversion
        content, code_blocks = self._extract_code_blocks(content)

        # Convert markdown to HTML
        html_content = self.md.convert(content)

        # Process admonitions
        html_content = self._process_admonitions(html_content)

        # Process images
        html_content = self._process_images(html_content, base_path)

        # Restore code blocks with Confluence macros
        html_content = self._restore_code_blocks(html_content, code_blocks)

        # Clean up the HTML to match Confluence's expectations
        html_content = html_content.replace(
            "&amp;", "&"
        ).replace(  # Confluence prefers unescaped ampersands
            "<br>", "<br />"
        )  # Use self-closing tags

        logger.debug("Markdown conversion completed")
        return html_content

    def convert_file(self: "MarkdownConverter", file_path: Path) -> str:
        """Convert a markdown file to Confluence storage format.

        Args:
            file_path: Path to the markdown file

        Returns:
            The converted content in Confluence storage format
        """
        logger.info(f"Converting markdown file: {file_path}")
        content = file_path.read_text(encoding="utf-8")
        return self.convert(content, base_path=file_path.parent)
