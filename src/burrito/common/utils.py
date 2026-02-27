import hashlib
import os
import pathlib
import platform
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from textwrap import dedent

from fastapi import Request

from burrito import __version__
from burrito.common.config import settings

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
PROMPT_DIR = pathlib.Path(__file__).parent.parent / "prompts"


from burrito.types.wire_api_params import WireApiParams
from burrito.types.wire_api_params_chat import WireApiParamsChat
from burrito.types.wire_api_params_responses import WireApiParamsResponses
from burrito.types.wire_api_params_messages import WireApiParamsMessages

def wire_api_label_from_params(params: WireApiParams) -> str
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

@lru_cache(maxsize=None)
def _read_file(path: pathlib.Path) -> str:
    return dedent(path.read_text(encoding="utf-8"))


def get_prompt(filename: str, extension: str = "md") -> str:
    file_path = PROMPT_DIR / f"{filename}.{extension.replace('.', '')}"
    if not file_path.is_file():
        raise FileNotFoundError(f"Prompt file {filename!r} not found in {PROMPT_DIR}")
    return _read_file(file_path)


def get_headers_to_forward(request: Request):
    split_comma = settings.BACKEND_FORWARD_HEADERS.split(",")
    split_colon = settings.BACKEND_FORWARD_HEADERS.split(";")
    headers_to_forward = [i.strip() for i in split_comma] + [
        i.strip() for i in split_colon
    ]
    return {
        k: v
        for k, v in request.headers.items()
        if k.title() in [h.title() for h in headers_to_forward]
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
    # Note: These may not work in all terminals.
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
