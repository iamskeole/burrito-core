import re

from typing import Any

from urllib.parse import quote, unquote

from gpt_oss.tools.simple_browser.simple_browser_tool import wrap_lines
from gpt_oss.tools.simple_browser.page_contents import (
    remove_unicode_smp,
    _replace_special_chars,
)
from gpt_oss.tools.simple_browser import SimpleBrowserTool
from burrito.tools.browser.backend import BurritoBackend

FIND_PAGE_LINK_FORMAT = "# 【{idx}†{title}】"
PARTIAL_INITIAL_LINK_PATTERN = re.compile(r"^[^【】]*】")
PARTIAL_FINAL_LINK_PATTERN = re.compile(
    r"【\d*(?:†(?P<content>[^†】]*)(?:†[^†】]*)?)?$"
)
LINK_PATTERN = re.compile(r"【\d+†(?P<content>[^†】]+)(?:†[^†】]+)?】")

CITATION_OUTPUT_PATTERN = re.compile(
    r"【(?P<cursor>\d+)†(?P<content>[^†】]+)(?:†[^†】]+)?】"
)
CLEANUP_PATTERN = re.compile(r"【\d+†(?P<content>[^†】]+)(?:†[^†】]+)?】")


def merge_lines_cited(lines_page: list[str], l_start: int, l_end: int) -> str:
    # 1. Get the slice
    lines_cited = lines_page[l_start:l_end]

    # 2. Robust Sentence Filtering (Added safety checks for empty/short lines)
    # Discard if starts with lowercase (partial sentence)
    if lines_cited and lines_cited[0] and lines_cited[0][0].islower():
        lines_cited = lines_cited[1:]

    # Discard if last line doesn't end in punctuation
    if lines_cited and lines_cited[-1] and lines_cited[-1][-1] not in ".!?\"'”":
        lines_cited = lines_cited[:-1]

    text_block = "".join(lines_cited)
    cleaned_text = CLEANUP_PATTERN.sub(r"\g<content>", text_block).strip()
    return cleaned_text or ""


def generate_highlight_url(base_url: str, lines_cited: str) -> str:
    # join and Clean AI markers
    # extract 3-word anchors
    # split by whitespace and filter out empty strings
    words = [w for w in lines_cited.split() if w]

    if not words:
        return base_url

    if len(words) <= 6:
        # If the text is short, just use the whole thing
        # We quote the whole string
        fragment = quote(" ".join(words))
    else:
        # Get first 3 and last 3 words
        # We strip non-alphanumeric chars from the edges of these words
        # to make the browser matching more "fuzzy" and reliable.
        def clean_anchor(word_list):
            # Join words, then URL encode
            s = " ".join(word_list)
            return quote(s)

        start_anchor = clean_anchor(words[:3])
        end_anchor = clean_anchor(words[-3:])

        # The comma is the special "start,end" delimiter for the browser
        fragment = f"{start_anchor},{end_anchor}"

    return f"{base_url}#:~:text={fragment}#:~:cite={lines_cited}"


class BurritoBrowser(SimpleBrowserTool):
    def __init__(self):
        super().__init__(backend=BurritoBackend())
        x = 1

    def augment_annotation(self, annotation: dict[str, Any]) -> dict[str, Any]:
        url = annotation["url"]
        page = self.tool_state.get_page_by_url(url)

        l_split = annotation["citation_marker"].split("-")
        l_start = int(l_split[0][1:])
        l_end = int(l_split[1][1:]) + 1
        lines_page = wrap_lines(text=page.text if page else "")

        cited_text = merge_lines_cited(lines_page, l_start, l_end)
        highlight_url = generate_highlight_url(url, cited_text)

        annotation["title"] = page.title if page else ""
        annotation["url"] = url
        annotation["highlight_url"] = highlight_url
        annotation["cited_text"] = cited_text
        return annotation

    def normalize_citations(
        self,
        old_content: str,
        hide_partial_citations: bool = False,
        current_citations: list[dict[str, Any]] = [],
    ) -> tuple[str, list[dict[str, Any]], bool]:
        """
        Returns a tuple of (new_message, annotations, has_partial_citations)
        - new_message: Message with citations replaced by ([domain](url))
        - annotations: list of dicts with start_index, end_index, and title (url)
        - has_partial_citations: whether the text includes an unfinished citation
        """

        has_partial_citations = (
            PARTIAL_FINAL_LINK_PATTERN.search(old_content) is not None
        )
        if hide_partial_citations and has_partial_citations:
            old_content = PARTIAL_FINAL_LINK_PATTERN.sub("", old_content)

        matches = []
        for match in CITATION_OUTPUT_PATTERN.finditer(old_content):
            cursor = match.group("cursor")
            content = match.group("content")
            start_idx = match.start()
            end_idx = match.end()
            matches.append(
                {
                    "cursor": cursor,
                    "content": content,
                    "start": start_idx,
                    "end": end_idx,
                }
            )

        # Build a mapping from cursor to url
        cursor_to_url = {}
        for idx, url in enumerate(self.tool_state.page_stack):
            cursor_to_url[str(idx)] = url

        def extract_domain(url):
            try:
                return unquote(url).split("/")[2]
            except Exception:
                return url

        new_content = ""
        last_idx = 0
        annotations = []

        cited_urls = set(i["url"] for i in current_citations)
        # running_offset = 0  # Offset due to length changes in replacements

        for m in matches:
            cursor = m["cursor"]
            url = cursor_to_url.get(cursor, "")
            url_clean = url.split("/find?pattern=")[0].rstrip("/")

            orig_start = m["start"]
            orig_end = m["end"]

            # Add text before the citation
            new_content += old_content[last_idx:orig_start]

            if url:
                domain = extract_domain(url)
                # replacement = f" ([{domain}]({url})) "
                annotation = {
                    "url": url_clean,
                    "type": "url_citation",
                    "domain": domain,
                    "citation_marker": m["content"],
                }
                annotation = self.augment_annotation(annotation)

                replacement = ""
                if annotation["url"] not in cited_urls:
                    # replacement = f" [[{len(current_citations)+1}]]({annotation['url']})"
                    replacement = f" [({domain.replace('www.', '')})]({annotation['url']})"
                else:
                    replacement = ""
                new_content += replacement

                # The start and end indices in the new content
                start_index = len(new_content)
                end_index = start_index + len(replacement)
                annotation["start_index"] = start_index
                annotation["end_index"] = end_index
                annotations.append(annotation)

            else:
                # Keep the original citation format if cursor is missing
                replacement = old_content[orig_start:orig_end]
                start_index = len(new_content)
                end_index = start_index + len(replacement)
                # No annotation for missing url, but could add if desired
                new_content += replacement

            last_idx = orig_end

        new_content += old_content[last_idx:]
        return new_content, annotations, has_partial_citations
