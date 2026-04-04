import hashlib
import os
import pathlib
import platform
import re
import subprocess
import sys
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from textwrap import dedent
from typing import Generic, Iterator, Optional, TypeVar

from fastapi import Request

from burrito import __version__
from burrito.common.config import list_from_cfg, settings
from burrito.types.wire_api_params import WireApiParams
from burrito.types.wire_api_params_chat import WireApiParamsChat
from burrito.types.wire_api_params_messages import WireApiParamsMessages
from burrito.types.wire_api_params_responses import WireApiParamsResponses

K = TypeVar("K")
V = TypeVar("V")

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
PROMPT_DIR = pathlib.Path(__file__).parent.parent / "prompts"


def wire_api_label_from_params(params: WireApiParams) -> str:
    match params:
        case WireApiParamsChat():
            w = "oai:chat"
        case WireApiParamsResponses():
            w = "oai:responses"
        case WireApiParamsMessages():
            w = "ant:messages"
        case _:
            w = "unknown"
    return w


@lru_cache(maxsize=128)
def _read_file(path: pathlib.Path) -> str:
    return dedent(path.read_text(encoding="utf-8"))


def get_prompt(filename: str, extension: str = "md") -> str:
    file_path = PROMPT_DIR / f"{filename}.{extension.replace('.', '')}"
    if not file_path.is_file():
        raise FileNotFoundError(f"Prompt file {filename!r} not found in {PROMPT_DIR}")
    return _read_file(file_path)


def get_headers_to_forward(request: Request):
    headers_to_forward = list_from_cfg(settings.BACKEND_FORWARD_HEADERS, "")
    return {
        k: v
        for k, v in request.headers.items()
        if k.title() in [h.title() for h in headers_to_forward or []]
    }


def random_uuid() -> str:
    return str(uuid.uuid4().hex)


def random_guid() -> str:
    return str(uuid.uuid4())


def yyyymmdd(in_utc: bool = False):
    now = datetime.now(tz=timezone.utc if in_utc else None)
    yy, mm, dd = now.year, str(now.month).zfill(2), str(now.day).zfill(2)
    return f"{yy}-{mm}-{dd}"


def unix_timestamp():
    now = datetime.now(tz=timezone.utc)
    return int(now.timestamp())


def unix_timestamp_in_ms():
    return int(time.time() * 1000)


def render_terminal_glyph(glyph: str, fallback: str) -> str:
    enc = sys.stdout.encoding or "utf-8"
    try:
        glyph.encode(enc, errors="strict")
        return glyph
    except (UnicodeEncodeError, LookupError):
        return fallback


def get_stable_machine_id():
    os_type = platform.system()
    try:
        if os_type == "Linux":
            if os.path.exists("/etc/machine-id"):
                return open("/etc/machine-id").read().strip()
            if os.path.exists("/var/lib/dbus/machine-id"):
                return open("/var/lib/dbus/machine-id").read().strip()

        elif os_type == "Windows":
            cmd = 'reg query "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid'
            output = subprocess.check_output(cmd, shell=True).decode()
            return output.split()[-1]

        elif os_type == "Darwin":  # macOS
            cmd = "ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID"
            output = subprocess.check_output(cmd, shell=True).decode()
            return output.split("=")[-1].strip().replace('"', "")

    except Exception:
        return f"{platform.processor()}-{os.cpu_count()}"


def get_system_fingerprint(version_string=__version__):
    machine_id = get_stable_machine_id()
    env_info = f"{platform.architecture()[0]}-{platform.python_version()}"
    combined = f"{machine_id}-{env_info}-{version_string}"
    fingerprint = hashlib.sha256(combined.encode()).hexdigest()
    return f"fp_{fingerprint[:12]}"


def simple_markdown_renderer(markdown_text):
    """
    A simple Markdown renderer that uses only the Python standard library.

    Args:
        markdown_text: A string containing Markdown formatted text.

    Returns:
        A string with basic terminal formatting.
    """
    # Define ANSI escape codes for basic styling
    styles = {
        "bold": "\033[1m",
        "underline": "\033[4m",
        "green": "\033[92m",
        "blue": "\033[94m",
        "end": "\033[0m",
    }

    # If not outputting to a TTY, disable styles
    if not sys.stdout.isatty():
        for key in styles:
            styles[key] = ""

    rendered_lines = []
    in_code_block = False

    for line in markdown_text.strip().split("\n"):
        # Code Blocks (```)
        if line.strip() == "```":
            in_code_block = not in_code_block
            rendered_lines.append(styles["green"] + "..." + styles["end"])
            continue

        if in_code_block:
            rendered_lines.append(styles["green"] + "    " + line + styles["end"])
            continue

        # Headers (e.g., #, ##, ###)
        header_match = re.match(r"^(#+)\s(.*)", line)
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2)
            if level == 1:
                rendered_lines.append(
                    f"{styles['bold']}{styles['underline']}{title}{styles['end']}\n"
                )
            else:
                rendered_lines.append(
                    f"{styles['bold']}{'  ' * (level - 1)}{title}{styles['end']}"
                )
            continue

        # Unordered Lists (*, -, +)
        ul_match = re.match(r"^\s*[\*\-\+]\s(.*)", line)
        if ul_match:
            item = ul_match.group(1)
            rendered_lines.append(f"  • {item}")
            continue

        # Ordered Lists (1., 2., 3.)
        ol_match = re.match(r"^\s*\d+\.\s(.*)", line)
        if ol_match:
            item = ol_match.group(1)
            rendered_lines.append(f"  {line.lstrip()}")
            continue

        # Blockquotes (>)
        bq_match = re.match(r"^>\s(.*)", line)
        if bq_match:
            quote = bq_match.group(1)
            rendered_lines.append(f"{styles['blue']}| {quote}{styles['end']}")
            continue

        # Regular text
        rendered_lines.append(line)

    return "\n".join(rendered_lines)


class LruDict(Generic[K, V]):
    """A size-limited LRU dictionary.

    Parameters
    ----------
    maxsize:
        The maximum number of items that the dictionary can hold.
        When this limit is reached, inserting a new item removes the
        least recently used (oldest) entry.
    """

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._data: OrderedDict[K, V] = OrderedDict()
        self._disabled = maxsize <= 0

    # ---------------------------------------------------------------------
    # Mapping interface
    # ---------------------------------------------------------------------
    def __setitem__(self, key: K, value: V) -> None:
        if self._disabled:
            return
        if key in self._data:
            # Existing key: update and mark as most recent.
            self._data.move_to_end(key)
        else:
            # New key: ensure capacity.
            if len(self._data) >= self.maxsize:
                # Evict least‑recently used item.
                self._data.popitem(last=False)
        self._data[key] = value

    def __getitem__(self, key: K) -> V:
        value = self._data[key]  # raises KeyError if missing
        self._data.move_to_end(key)
        return value

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return default

    def __contains__(self, key: K) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def __iter__(self) -> Iterator[K]:
        return iter(self._data)

    def __repr__(self) -> str:
        return f"LruDict(maxsize={self.maxsize}, data={dict(self._data)})"


def grammar_is_likely_lark(grammar_str: str) -> bool:
    """From vLLM: Check if grammar appears to use Lark syntax."""
    if not grammar_str or not isinstance(grammar_str, str):
        return False
    for line in grammar_str.split("\n"):
        line = re.sub(r"(#|//).*$", "", line).strip()
        if not line:
            continue
        if "::=" in line:
            return False
    return True


def lark_to_gbnf(grammar: str) -> str:
    """Converter that handles Regex, Imports, Aliases, and Underscores."""

    # Check if already valid GBNF
    has_gbnf_root = "root ::=" in grammar
    has_lark_rules = bool(re.search(r"^\s*[a-zA-Z0-9_]+\s*:", grammar, re.MULTILINE))
    if has_gbnf_root and not has_lark_rules:
        return grammar.strip()

    lines = grammar.strip().splitlines()
    gbnf_lines = ["root ::= begin-patch hunk+ end-patch"]  # Updated root rule

    lark_common_imports = {
        "common.LF": r'LF ::= "\n"',
        "common.CR": r'CR ::= "\r"',
        "common.WS": r"WS ::= [ \t\n\r]+",
        "common.DIGIT": r"DIGIT ::= [0-9]",
    }
    imports_to_add = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("start:"):
            continue

        if stripped.startswith("%import"):
            match = re.search(r"%import\s+([a-zA-Z0-9_.]+)", stripped)
            if match and match.group(1) in lark_common_imports:
                imports_to_add.append(lark_common_imports[match.group(1)])
            continue

        line = re.sub(r"\s*->\s*[a-zA-Z0-9_]+", "", line)
        line = re.sub(r"^(\s*[a-zA-Z0-9_]+)\s*:", r"\1 ::=", line)
        line = line.replace(r"/(.+)/", r"[^\n]+")
        line = line.replace(r"/(.*)/", r"[^\n]*")
        line = re.sub(r"/([^/]+)/", lambda m: m.group(1).replace(".", r"[^\n]"), line)

        # Split by quotes to avoid replacing underscores inside literal strings
        parts = re.split(r'("[^"]*")', line)
        for i in range(0, len(parts), 2):
            # Even indexes are outside quotes: replace underscores
            parts[i] = parts[i].replace("_", "-")
        line = "".join(parts)
        # --------------------------------------------------

        gbnf_lines.append(line)

    if imports_to_add:
        gbnf_lines.append("")
        gbnf_lines.extend(list(set(imports_to_add)))

    return "\n".join(gbnf_lines)


bootstrap_pip = """
import sys
import subprocess

def _ensure_pip():
    try:
        import pip  # noqa: F401
    except ImportError:
        try:
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
        except Exception:
            # Fallback: try get-pip.py if ensurepip is unavailable
            try:
                subprocess.check_call([
                    sys.executable, "-c",
                    "import urllib.request; exec(urllib.request.urlopen('https://bootstrap.pypa.io/get-pip.py').read())"
                ])
            except Exception:
                pass  # give up silently

_ensure_pip()
"""


def minify_prompt_aggressive(text: str) -> str:
    """
    Removes ALL redundant whitespace, including newlines.
    Converts the entire text into a single line.
    """
    return " ".join(text.split())


def minify_prompt_safe(text: str) -> str:
    """
    Removes redundant spaces and empty lines, but preserves
    single line breaks for readability and markdown structure.
    """
    # 1. Remove leading/trailing spaces and tabs on every line
    text = re.sub(r"^[ \t]+|[ \t]+$", "", text, flags=re.MULTILINE)

    # 2. Collapse multiple spaces/tabs into a single space
    text = re.sub(r"[ \t]+", " ", text)

    # 3. Collapse multiple empty lines into a single newline
    text = re.sub(r"\n+", "\n", text)

    # 4. Strip final leading/trailing whitespace from the whole string
    return text.strip()


def minify_prompt_extreme(text: str) -> str:
    """
    Aggressively minifies prompt text while avoiding common footguns.
    Safely handles English prose, string literals, commas, and colons.
    """
    # 1. Collapse all whitespace, tabs, and newlines to a single space
    text = " ".join(text.split())

    # 2. Glue consecutive structural brackets/braces.
    # Matches a space ONLY if it is flanked by brackets/braces on BOTH sides.
    # Fixes the `] } } ]` bloat but avoids altering strings like `"Hello { name }"`
    text = re.sub(r"(?<=[\[\]\{\}])\s+(?=[\[\]\{\}])", "", text)

    # 3. Strip spaces explicitly around LLM special tokens (e.g., <|end|>, <|user|>)
    text = re.sub(r"\s*(<\|.*?\|>)\s*", r"\1", text)

    return text
