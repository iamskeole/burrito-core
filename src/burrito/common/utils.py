import re
import sys
import time
import uuid
import hashlib
import platform
import subprocess
import os
from datetime import datetime, timezone
from typing import get_type_hints

from burrito import __version__

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def random_uuid() -> str:
    return str(uuid.uuid4().hex)


def yyyymmdd():
    now = datetime.now(tz=timezone.utc)
    yy, mm, dd = now.year, str(now.month).zfill(2), str(now.day).zfill(2)
    return f"{yy}-{mm}-{dd}"


def unix_timestamp():
    now = datetime.now(tz=timezone.utc)
    return int(now.timestamp())


def unix_timestamp_in_ms():
    return int(time.time() * 1000)


def populate_openai_typed_dict(typed_dict_class: type, partial_data: dict) -> dict:
    all_field_names = get_type_hints(typed_dict_class).keys()
    complete_dict = {key: None for key in all_field_names}
    complete_dict.update(partial_data)
    return complete_dict


def get_stable_machine_id():
    """Gets a unique ID that stays the same for the hardware OS instance."""
    os_type = platform.system()

    try:
        if os_type == "Linux":
            # Standard on most Linux distros
            if os.path.exists("/etc/machine-id"):
                return open("/etc/machine-id").read().strip()
            if os.path.exists("/var/lib/dbus/machine-id"):
                return open("/var/lib/dbus/machine-id").read().strip()

        elif os_type == "Windows":
            # Registry key for the specific Windows installation
            cmd = 'reg query "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid'
            output = subprocess.check_output(cmd, shell=True).decode()
            return output.split()[-1]

        elif os_type == "Darwin":  # macOS
            # Hardware UUID from system_profiler
            cmd = "ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID"
            output = subprocess.check_output(cmd, shell=True).decode()
            return output.split("=")[-1].strip().replace('"', "")

    except Exception:
        # Fallback to something stable but less unique (CPU + Core count)
        return f"{platform.processor()}-{os.cpu_count()}"


def get_system_fingerprint(version_string=__version__):
    # 1. Identify the Machine
    machine_id = get_stable_machine_id()

    # 2. Identify the Environment (Python version + Architecture)
    # We include this because code runs differently on 32-bit vs 64-bit or Py 3.10 vs 3.12
    env_info = f"{platform.architecture()[0]}-{platform.python_version()}"

    # Combine and hash
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


def clean_traceback(tb: str) -> str:
    # strip ansi colors
    tb = ANSI_RE.sub("", tb)
    # remove jupyter cell references eg 'Cell In[25], line 1'
    tb = re.sub(r"^\s*Cell In\[\d+\], line \d+\n", "", tb, flags=re.MULTILINE)
    # remove the caret line pointing to syntax column
    tb = re.sub(r"^\s*\^.*\n", "", tb, flags=re.MULTILINE)
    return tb.strip()
