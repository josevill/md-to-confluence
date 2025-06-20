#!/usr/bin/env python3
"""Debug script to troubleshoot markdown conversion issues."""

import logging
from pathlib import Path

from src.confluence.converter import MarkdownConverter

# Set up logging to see what's happening
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")


def debug_conversion():
    """Debug the markdown conversion for the problematic file."""

    # Path to the problematic file
    markdown_file = Path("docs/md-to-confluence project.md")

    if not markdown_file.exists():
        print(f"File not found: {markdown_file}")
        return

    print(f"Converting file: {markdown_file}")
    print("=" * 50)

    # Initialize converter
    converter = MarkdownConverter()

    # Read the file content
    content = markdown_file.read_text(encoding="utf-8")
    print(f"Original markdown content length: {len(content)} characters")
    print("=" * 50)

    try:
        # Convert to Confluence storage format
        storage_format = converter.convert(content, base_path=markdown_file.parent)

        print("CONVERSION SUCCESSFUL!")
        print("=" * 50)
        print("Converted XHTML:")
        print(storage_format)
        print("=" * 50)

        # Save to file for inspection
        output_file = Path("debug_output.xml")
        output_file.write_text(storage_format, encoding="utf-8")
        print(f"XHTML saved to: {output_file}")

        # Check for common issues
        check_common_issues(storage_format)

    except Exception as e:
        print(f"CONVERSION FAILED: {e}")
        import traceback

        traceback.print_exc()


def check_common_issues(xhtml_content):
    """Check for common XHTML issues that might cause Confluence errors."""

    print("\nChecking for common issues:")
    print("-" * 30)

    issues = []

    # Check for unclosed structured macros
    import re

    # Find all opening structured-macro tags
    opening_macros = re.findall(r"<ac:structured-macro[^>]*>", xhtml_content)
    closing_macros = re.findall(r"</ac:structured-macro>", xhtml_content)

    if len(opening_macros) != len(closing_macros):
        issues.append(
            f"Mismatched structured-macro tags: {len(opening_macros)} opening, {len(closing_macros)} closing"
        )

    # Check for malformed XML tags
    if "</xml>" in xhtml_content:
        issues.append("Found unexpected </xml> tag")

    # Check for unclosed CDATA sections
    cdata_open = xhtml_content.count("<![CDATA[")
    cdata_close = xhtml_content.count("]]>")
    if cdata_open != cdata_close:
        issues.append(f"Mismatched CDATA sections: {cdata_open} opening, {cdata_close} closing")

    # Check for line numbers around error (line 116)
    lines = xhtml_content.split("\n")
    if len(lines) >= 116:
        print("Content around line 116 (where error occurred):")
        start_line = max(0, 116 - 5)
        end_line = min(len(lines), 116 + 5)
        for i in range(start_line, end_line):
            marker = " --> " if i == 115 else "     "  # Line 116 is index 115
            print(f"{i+1:3d}{marker}{lines[i]}")

    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("No obvious XHTML issues detected")


if __name__ == "__main__":
    debug_conversion()
