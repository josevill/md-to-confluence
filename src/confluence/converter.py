"""Markdown to Confluence XHTML converter."""

import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

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

    # Image template for attachments
    IMAGE_ATTACHMENT_TEMPLATE = """<ac:image ac:alt="{alt_text}"{width_attr}>
        <ri:attachment ri:filename="{filename}"/>
    </ac:image>"""

    # Fallback template for failed image uploads
    IMAGE_FALLBACK_TEMPLATE = """<ac:structured-macro ac:name="info">
        <ac:rich-text-body>
            <p><strong>Image not available:</strong> {original_name}</p>
            {alt_text_paragraph}
        </ac:rich-text-body>
    </ac:structured-macro>"""

    # Supported image formats
    SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

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

    def _extract_local_images(
        self, content: str, base_path: Optional[Path] = None
    ) -> Tuple[str, Dict]:
        """Extract local image references and replace with placeholders.

        Args:
            content: The markdown content
            base_path: Base path for resolving relative image paths

        Returns:
            Tuple containing:
                - Content with local images replaced by placeholders
                - Dictionary mapping placeholders to image info
        """
        local_images = {}

        # Pattern for markdown images: ![alt](path) or ![alt](path "title")
        pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+?)(?:\s+"([^"]*)")?\)')

        def replace_image(match):
            alt_text = match.group(1) or ""
            image_path = match.group(2)
            title = match.group(3) or ""

            # Check if it's a local image (not http/https)
            if not image_path.startswith(("http://", "https://", "data:")):
                # Resolve relative path if base_path provided
                if base_path:
                    full_path = base_path / image_path
                else:
                    full_path = Path(image_path)

                # Check if file exists and is supported format
                if full_path.exists() and self._is_supported_image(full_path):
                    placeholder = f"LOCAL_IMAGE_{len(local_images)}"
                    local_images[placeholder] = {
                        "path": full_path,
                        "alt": alt_text,
                        "title": title,
                        "original_name": image_path,
                        "filename": full_path.name,
                    }
                    logger.debug(f"Found local image: {image_path} -> {full_path}")
                    return placeholder
                else:
                    logger.warning(f"Image not found or unsupported format: {image_path}")

            # Keep external images or unsupported files as-is
            return match.group(0)

        processed_content = pattern.sub(replace_image, content)
        return processed_content, local_images

    def _is_supported_image(self, file_path: Path) -> bool:
        """Check if the image format is supported by Confluence.

        Args:
            file_path: Path to the image file

        Returns:
            True if the image format is supported
        """
        return file_path.suffix.lower() in self.SUPPORTED_IMAGE_FORMATS

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

    def _restore_local_images(
        self, content: str, local_images: Dict, uploaded_attachments: Dict[str, bool]
    ) -> str:
        """Replace image placeholders with Confluence attachment macros or fallbacks.

        Args:
            content: Content with image placeholders
            local_images: Dictionary mapping placeholders to image info
            uploaded_attachments: Dictionary of successfully uploaded filenames

        Returns:
            Content with images restored as Confluence macros or fallbacks
        """
        for placeholder, image_info in local_images.items():
            filename = image_info["filename"]
            alt_text = image_info["alt"]

            if uploaded_attachments.get(filename, False):
                # Create Confluence attachment image macro
                width_attr = ' ac:width="600"' if alt_text else ""  # Default width for images
                image_macro = self.IMAGE_ATTACHMENT_TEMPLATE.format(
                    alt_text=alt_text, filename=filename, width_attr=width_attr
                )
                content = content.replace(placeholder, image_macro)
                logger.debug(f"Replaced {placeholder} with attachment macro for {filename}")
            else:
                # Create fallback for failed upload
                fallback = self._create_image_fallback(image_info)
                content = content.replace(placeholder, fallback)
                logger.warning(f"Replaced {placeholder} with fallback for {filename}")

        return content

    def _create_image_fallback(self, image_info: Dict) -> str:
        """Create a fallback placeholder for failed image uploads.

        Args:
            image_info: Dictionary containing image information

        Returns:
            Confluence macro for the image fallback
        """
        original_name = image_info["original_name"]
        alt_text = image_info["alt"]

        alt_text_paragraph = f"<p><em>{alt_text}</em></p>" if alt_text else ""

        return self.IMAGE_FALLBACK_TEMPLATE.format(
            original_name=original_name, alt_text_paragraph=alt_text_paragraph
        )

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

        # Escape any Confluence macro syntax that appears in regular text
        # This prevents accidentally creating malformed macros
        html_content = self._escape_confluence_syntax(html_content)

        # logger.info(f"Converted content: {html_content}")
        logger.debug("Markdown conversion completed")
        return html_content

    def convert_with_images(
        self, content: str, base_path: Optional[Path] = None
    ) -> Tuple[str, Dict]:
        """Convert Markdown content and extract local images for separate processing.

        Args:
            content: The markdown content to convert
            base_path: Optional base path for resolving relative paths

        Returns:
            Tuple containing:
                - The converted content with image placeholders
                - Dictionary of local images to be uploaded
        """
        logger.info("Converting markdown content with image extraction")

        # Extract code blocks before markdown conversion
        content, code_blocks = self._extract_code_blocks(content)

        # Extract local images before markdown conversion
        content, local_images = self._extract_local_images(content, base_path)

        # Convert markdown to HTML
        html_content = self.md.convert(content)

        # Process admonitions
        html_content = self._process_admonitions(html_content)

        # Process remaining external images (non-local ones)
        html_content = self._process_images(html_content, base_path)

        # Restore code blocks with Confluence macros
        html_content = self._restore_code_blocks(html_content, code_blocks)

        # Clean up the HTML to match Confluence's expectations
        html_content = html_content.replace(
            "&amp;", "&"
        ).replace(  # Confluence prefers unescaped ampersands
            "<br>", "<br />"
        )  # Use self-closing tags

        # Escape any Confluence macro syntax that appears in regular text
        html_content = self._escape_confluence_syntax(html_content)

        logger.debug(f"Markdown conversion completed with {len(local_images)} local images")
        return html_content, local_images

    def finalize_content_with_images(
        self, content: str, local_images: Dict, uploaded_attachments: Dict[str, bool]
    ) -> str:
        """Finalize content by replacing image placeholders with proper macros.

        Args:
            content: Content with image placeholders
            local_images: Dictionary of local images info
            uploaded_attachments: Dictionary of successfully uploaded filenames

        Returns:
            Final content with image macros or fallbacks
        """
        logger.debug("Finalizing content with image attachments")
        return self._restore_local_images(content, local_images, uploaded_attachments)

    def _escape_confluence_syntax(self: "MarkdownConverter", content: str) -> str:
        """Escape Confluence macro syntax that appears in regular text.

        Args:
            content: The HTML content

        Returns:
            Content with Confluence syntax properly escaped
        """
        # Find any ac:structured-macro tags that are not properly closed
        # and escape them to prevent malformed XML

        # Pattern to match incomplete macro syntax (missing closing tag)
        # This matches things like: <ac:structured-macro ac:name="code">...)
        # but NOT complete macros that have proper closing tags
        import re

        # Look for structured-macro openings that don't have corresponding closings
        def escape_incomplete_macros(match):
            macro_text = match.group(0)
            # Check if this appears to be part of documentation text rather than a real macro
            # Real macros should have proper parameter structure and closing tags
            if "..." in macro_text or not re.search(
                r"</ac:structured-macro>", content[match.end() : match.end() + 500]
            ):
                # This looks like documentation text, escape it
                return macro_text.replace("<", "&lt;").replace(">", "&gt;")
            return macro_text

        # Find standalone macro syntax that looks like documentation
        pattern = r"<ac:structured-macro[^>]*>[^<]*\.\.\.[^<]*\)"
        content = re.sub(pattern, escape_incomplete_macros, content)

        return content

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
