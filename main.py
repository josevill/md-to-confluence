"""Hello"""

from pathlib import Path

from src.confluence.converter import MarkdownConverter

converter = MarkdownConverter()
result = converter.convert_file(Path("README.md"))
print(result)
