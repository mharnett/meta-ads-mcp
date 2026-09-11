"""README must carry a deprecation notice pointing at mcp-meta-ads-incrementality.

This repo is being retired in favor of `mharnett/mcp-meta-ads-incrementality`
(drak-stack-monorepo's internal replacement). Anyone opening this README
should immediately see that it's deprecated, what replaces it, and the two
confirmed capability gaps the replacement doesn't cover yet, rather than
silently building against a retired server.
"""
import re
from pathlib import Path

README = (Path(__file__).parent.parent / "README.md").read_text()


def _section_between_title_and_toc():
    """The notice must sit after the title, before the Table of Contents heading."""
    toc_match = re.search(r"^## Table of Contents", README, re.MULTILINE)
    assert toc_match, "README has no '## Table of Contents' heading to anchor against"
    return README[:toc_match.start()]


def test_readme_has_deprecation_notice_before_toc():
    section = _section_between_title_and_toc()
    assert "deprecat" in section.lower(), (
        "No deprecation notice found between the title and the Table of Contents"
    )


def test_deprecation_notice_names_the_replacement():
    section = _section_between_title_and_toc()
    assert "mcp-meta-ads-incrementality" in section
    assert "mharnett/mcp-meta-ads-incrementality" in section


def test_deprecation_notice_names_both_capability_gaps():
    section = _section_between_title_and_toc()
    lowered = section.lower()
    assert "image" in lowered and "video" in lowered and "librar" in lowered, (
        "Missing the image/video library listing capability gap"
    )
    assert "asset_customization_rules" in section, (
        "Missing the asset_customization_rules / placement-specific creative gap"
    )
