"""PLAN 2.4 — deterministic markdown-subset renderer (RP-2)."""

from __future__ import annotations

from core import report


def test_headers_h1_h2_h3():
    html = report.md_subset_to_html("# One\n\n## Two\n\n### Three")
    assert "<h1>One</h1>" in html
    assert "<h2>Two</h2>" in html
    assert "<h3>Three</h3>" in html


def test_paragraphs():
    html = report.md_subset_to_html("hello world\n\nsecond graf")
    assert "<p>hello world</p>" in html
    assert "<p>second graf</p>" in html


def test_bullet_and_numbered_lists():
    html = report.md_subset_to_html("- a\n- b\n\n1. one\n2. two")
    assert "<ul>" in html and "<li>a</li>" in html and "<li>b</li>" in html
    assert "<ol>" in html and "<li>one</li>" in html and "<li>two</li>" in html


def test_pipe_table_with_alignment_row():
    md = "| h1 | h2 |\n| --- | ---: |\n| a | b |"
    html = report.md_subset_to_html(md)
    assert "<table>" in html
    assert "<th>h1</th>" in html
    assert "<td>a</td>" in html
    assert "---" not in html


def test_fenced_code_escapes_script():
    md = "```\n<script>alert(1)</script>\n```"
    html = report.md_subset_to_html(md)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<pre>" in html and "<code>" in html


def test_blockquote():
    html = report.md_subset_to_html("> quoted text")
    assert "<blockquote>" in html
    assert "quoted text" in html


def test_bold_italic_inline_code():
    html = report.md_subset_to_html("**bold** and *italic* and `code`")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<code>code</code>" in html


def test_raw_html_in_prose_is_escaped():
    html = report.md_subset_to_html("say <b>hi</b> there")
    assert "<b>hi</b>" not in html
    assert "&lt;b&gt;hi&lt;/b&gt;" in html


def test_out_of_subset_degrades_to_escaped_pre():
    md = "<div class=\"x\">\nhello\n</div>"
    html = report.md_subset_to_html(md)
    assert "<pre>" in html
    assert "&lt;div" in html
    assert "<div" not in html
    # still well-formed enough to contain the escaped payload
    assert "hello" in html


def test_renderer_is_deterministic():
    md = "# T\n\n- a\n- b\n\n| x | y |\n| --- | --- |\n| 1 | 2 |\n"
    assert report.md_subset_to_html(md) == report.md_subset_to_html(md)
