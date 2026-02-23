import logging
import re

from typing import Any, AsyncIterator, Literal

from urllib.parse import quote, unquote

from aiohttp import ClientSession, ClientTimeout

from burrito.tools.browser.backend import BurritoBrowserBackend

from gpt_oss.tools.simple_browser.simple_browser_tool import (
    wrap_lines,
    function_the_model_can_call,
    handle_errors,
    BackendError,
)

from gpt_oss.tools.simple_browser.backend import VIEW_SOURCE_PREFIX
from gpt_oss.tools.simple_browser import SimpleBrowserTool
from gpt_oss.tools.simple_browser.simple_browser_tool import ToolUsageError
from gpt_oss.tools.simple_browser.page_contents import Extract, PageContents
from gpt_oss.tools.simple_browser.backend import maybe_truncate
from openai_harmony import ToolNamespaceConfig, Message

from gpt_oss.tools.simple_browser.simple_browser_tool import (
    PARTIAL_FINAL_LINK_PATTERN,
    CITATION_OUTPUT_PATTERN,
)

from burrito.prompts import (
    browser_tool_description,
    browser_search_prompt,
    browser_open_prompt,
)

from burrito.common.config import settings

CLEANUP_PATTERN = re.compile(r"【\d+†(?P<content>[^†】]+)(?:†[^†】]+)?】")

TIMEOUT_FETCH = settings.BROWSER_TIMEOUT_FETCH
TIMEOUT_SEARCH = settings.BROWSER_TIMEOUT_SEARCH

logger = logging.getLogger("browser_backend")


def merge_lines_cited(lines_page: list[str], l_start: int, l_end: int) -> str:
    lines_cited = lines_page[l_start:l_end]

    if lines_cited and lines_cited[0] and lines_cited[0][0].islower():
        lines_cited = lines_cited[1:]

    if lines_cited and lines_cited[-1] and lines_cited[-1][-1] not in ".!?\"'”":
        lines_cited = lines_cited[:-1]

    text_block = "".join(lines_cited)
    cleaned_text = CLEANUP_PATTERN.sub(r"\g<content>", text_block).strip()
    return cleaned_text or ""


def generate_highlight_url(base_url: str, lines_cited: str) -> str:
    words = [w for w in lines_cited.split() if w]

    if not words:
        return base_url

    if len(words) <= 6:
        fragment = quote(" ".join(words))
    else:

        def clean_anchor(word_list):
            s = " ".join(word_list)
            return quote(s)

        start_anchor = clean_anchor(words[:3])
        end_anchor = clean_anchor(words[-3:])
        fragment = f"{start_anchor},{end_anchor}"

    return f"{base_url}#:~:text={fragment}"


class BurritoBrowser(SimpleBrowserTool):
    backend: BurritoBrowserBackend

    def __init__(self):
        super().__init__(backend=BurritoBrowserBackend())

    def patch_search_tool(self, config: ToolNamespaceConfig):
        _tool = None
        for i in config.tools:
            if i.name == "search":
                _tool = i
                break

        if _tool is None or _tool.parameters is None:
            return

        _tool.parameters["properties"]["query"] = {
            "type": "string",
            "description": browser_search_prompt.query_description,
        }

        _tool.parameters["properties"]["source"] = {
            "type": "string",
            "description": browser_search_prompt.source_description,
            "enum": ["general", "news", "it", "science", "files", "social media"],
        }
        _tool.parameters["properties"]["locale"] = {
            "type": "string",
            "description": browser_search_prompt.locale_description,
        }
        _tool.parameters["properties"]["language"] = {
            "type": "string",
            "description": browser_search_prompt.language_description,
        }
        _tool.parameters["properties"]["time_range"] = {
            "type": "string",
            "enum": ["day", "week", "month", "year", "alltime"],
            "description": "Restricts search results where relevant.",
        }
        _tool.parameters["required"] = [
            "query",
            "source",
            "locale",
            "language",
            "time_range",
        ]
        return config

    def patch_open_tool(self, config: ToolNamespaceConfig):
        _tool = None
        for i in config.tools:
            if i.name == "open":
                _tool = i
                break

        if _tool is None or _tool.parameters is None:
            return

        _tool.parameters["properties"]["is_docs_website"] = {
            "type": "boolean",
            "description": browser_open_prompt.is_docs_site_description,
        }
        _tool.parameters["required"] = ["is_docs_website"]
        return config

    def patch_tool_description(self, config: ToolNamespaceConfig):
        config.description = browser_tool_description.text
        return config

    @property
    def tool_config(self) -> ToolNamespaceConfig:
        config = super().tool_config
        self.patch_tool_description(config)
        self.patch_search_tool(config)
        self.patch_open_tool(config)
        return config

    @function_the_model_can_call
    @handle_errors
    async def search(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        query: str,
        locale: str = "en-US",
        language: str = "en",
        time_range: Literal["day", "week", "month", "year", "alltime"] = "alltime",
        topn: int = 10,
        top_n: int = 10,
        source: str | None = None,
    ) -> AsyncIterator[Message]:
        limit = topn if topn != 10 else top_n

        try:
            async with ClientSession(
                timeout=ClientTimeout(total=TIMEOUT_SEARCH)
            ) as session:
                search_page = await self.backend.search(
                    query=query,
                    topn=limit,
                    session=session,
                    locale=locale,
                    language=language,
                    time_range=time_range,
                    source=source,
                )
        except Exception as e:
            msg = f"{e.__class__} | {e.__doc__}" + maybe_truncate(str(e))
            raise BackendError(f"Error during search for `{query}`: {msg}") from e

        self.tool_state.add_page(search_page)
        yield await self.show_page_safely(loc=0)

    async def _open_url(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, url: str, direct_url_open: bool, is_docs_website: bool
    ) -> PageContents:
        """Use the cache, if available."""
        backend: BurritoBrowserBackend = self.backend
        # direct_url_open should be regarded as a refresh
        if not direct_url_open and (page := self.tool_state.get_page_by_url(url)):
            assert page.url == url
            return page

        try:
            async with ClientSession(
                timeout=ClientTimeout(total=TIMEOUT_FETCH)
            ) as session:
                page = await backend.fetch(url, is_docs_website, session=session)
            return page
        except Exception as e:
            msg = maybe_truncate(str(e))
            raise BackendError(
                f"Error fetching URL `{maybe_truncate(url)}`: {msg}"
            ) from e

    @function_the_model_can_call
    @handle_errors
    async def open(
        self,
        id: int | str = -1,
        cursor: int = -1,
        loc: int = -1,
        num_lines: int = -1,
        view_source: bool = False,
        source: str | None = None,
        is_docs_website: bool = False,
    ) -> AsyncIterator[Message]:
        curr_page: PageContents | None = None
        stay_on_current_page = False
        direct_url_open = False

        if isinstance(id, str):
            snippet = None
            url = id
            direct_url_open = True
        else:  # Operate on a previously opened page
            curr_page = self.tool_state.get_page(cursor)

            if id >= 0:  # click a link
                try:
                    url = curr_page.urls[str(id)]
                except KeyError as e:
                    raise ToolUsageError(f"Invalid link id `{id}`.") from e
                snippet = (curr_page.snippets or {}).get(str(id))
                if snippet and curr_page.url == "":
                    # current page is a search result page
                    assert isinstance(snippet, Extract)
            else:  # navigate to new position on the current page
                if not view_source:
                    stay_on_current_page = True
                url = curr_page.url
                snippet = None

        new_page: PageContents
        if view_source:
            url = f"{VIEW_SOURCE_PREFIX}{url}"
            snippet = None
        if stay_on_current_page:
            assert curr_page is not None
            new_page = curr_page
        else:
            new_page = await self._open_url(url, direct_url_open, is_docs_website)

        self.tool_state.add_page(new_page)

        if loc < 0:  # unset
            if snippet is not None and snippet.line_idx is not None:
                loc = snippet.line_idx
                if loc > 4:
                    loc -= 4
            else:
                loc = 0

        yield await self.show_page_safely(loc=loc, num_lines=num_lines)

    # TODO: figure out why line split fails (very infrequently, but it does) and fix it.. somehow
    def augment_annotation(self, annotation: dict[str, Any]) -> dict[str, Any]:
        url = annotation["url"]
        page = self.tool_state.get_page_by_url(url)

        try:
            l_split = annotation["citation_marker"].split("-")
        except Exception as e:
            return annotation
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

    def normalize_citations(  # pyright: ignore[reportIncompatibleMethodOverride]
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

        cited_urls = []
        for i in current_citations:
            url_to_index = i["url"].split("/find?pattern=")[0].rstrip("/")
            if VIEW_SOURCE_PREFIX in url_to_index:
                url_to_index = url_to_index.replace(VIEW_SOURCE_PREFIX, "")
            if url_to_index not in cited_urls:
                cited_urls.append(url_to_index)

        # running_offset = 0  # Offset due to length changes in replacements
        for m in matches:
            cursor = m["cursor"]
            url = cursor_to_url.get(cursor, "")
            url_clean = url.split("/find?pattern=")[0].rstrip("/")

            if VIEW_SOURCE_PREFIX in url_clean:
                url_clean = url_clean.replace(VIEW_SOURCE_PREFIX, "")

            orig_start = m["start"]
            orig_end = m["end"]

            # Add text before the citation
            new_content += old_content[last_idx:orig_start]

            if url:
                domain = extract_domain(url)
                annotation = {
                    "url": url_clean,
                    "type": "url_citation",
                    "domain": domain,
                    "citation_marker": m["content"],
                }
                annotation = self.augment_annotation(annotation)

                if url_clean not in cited_urls:
                    citation_index = len(cited_urls) + 1
                else:
                    citation_index = cited_urls.index(url_clean) + 1

                replacement = f" [[{citation_index}]]({url_clean})"
                if cited_urls and url_clean == cited_urls[-1]:
                    # avoid back to back citations eg [1][1][2]
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
