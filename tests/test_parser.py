"""Tests for the parser — verified without network or embedding dependencies."""
from mindmark.parser import parse_bookmarks


SAMPLE = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1" LAST_MODIFIED="2" PERSONAL_TOOLBAR_FOLDER="true">Bar</H3>
    <DL><p>
        <DT><H3 ADD_DATE="3">Work</H3>
        <DL><p>
            <DT><A HREF="https://eng.ms/docs/kusto" ADD_DATE="10">Kusto Access Guide</A>
            <DT><A HREF="https://dev.azure.com/foo">Azure DevOps</A>
        </DL><p>
        <DT><H3>Personal</H3>
        <DL><p>
            <DT><A HREF="https://travel.state.gov/visa">Visa Status</A>
        </DL><p>
        <DT><A HREF="https://example.com/top">Top-level bar bookmark</A>
    </DL><p>
</DL><p>
"""


def test_parses_titles_and_urls():
    bms = parse_bookmarks(SAMPLE)
    urls = {b.url: b for b in bms}
    assert "https://eng.ms/docs/kusto" in urls
    assert urls["https://eng.ms/docs/kusto"].title == "Kusto Access Guide"
    assert urls["https://dev.azure.com/foo"].title == "Azure DevOps"
    assert urls["https://travel.state.gov/visa"].title == "Visa Status"


def test_folder_paths_are_preserved():
    bms = parse_bookmarks(SAMPLE)
    by_url = {b.url: b for b in bms}
    assert by_url["https://eng.ms/docs/kusto"].folder_path == "Bar/Work"
    assert by_url["https://travel.state.gov/visa"].folder_path == "Bar/Personal"
    assert by_url["https://example.com/top"].folder_path == "Bar"


def test_deduplicates_by_url():
    html = SAMPLE + '<DT><A HREF="https://eng.ms/docs/kusto">duplicate</A>'
    bms = parse_bookmarks(html)
    assert sum(1 for b in bms if b.url == "https://eng.ms/docs/kusto") == 1


def test_embedding_text_is_informative():
    bms = parse_bookmarks(SAMPLE)
    k = next(b for b in bms if "kusto" in b.url)
    t = k.embedding_text()
    assert "Kusto Access Guide" in t
    assert "Bar/Work" in t
    assert "eng.ms" in t
