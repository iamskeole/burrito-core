from typing import TYPE_CHECKING, List, Optional

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.types.adapter import AdapterConversationState
from burrito.types.adapter.adapter_create_params_chat import AdapterFunctionToolChat
from burrito.types.adapter.adapter_create_params_responses import (
    AdapterCustomToolResponses,
    AdapterFunctionToolResponses,
)
from burrito.types.adapter.adapter_tool_namespace import AdapterToolNamespace
from burrito.types.sandbox.sandbox_run_code_request import SandboxRequest, SandboxResponse

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler

import ast
import traceback
from contextlib import redirect_stdout
from io import StringIO


def run(code: str):
    """
    Run arbitrary Python code in a clean local namespace,
    capture stdout, and return (result, stdout, error).
    """
    ns = {}

    try:
        tree = ast.parse(code, mode="exec")
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = tree.body[-1]
            assign = ast.Assign(
                targets=[ast.Name("_result", ast.Store())], value=last.value
            )
            # copy position info so Python >=3.11 doesn’t complain
            ast.copy_location(assign, last)
            tree.body[-1] = assign
            ast.fix_missing_locations(tree)
        code_obj = compile(tree, "<assistant>", "exec")
    except SyntaxError:
        return None, "", traceback.format_exc()

    buf = StringIO()
    err = None
    try:
        with redirect_stdout(buf):
            exec(code_obj, ns)
    except Exception:
        err = traceback.format_exc()

    return ns.get("_result"), buf.getvalue(), err


class ToolHandler:
    def __init__(self, manager: "AdapterStateHandler"):
        self.manager = manager
        self.namespaces: List[str] = []
        self.tools: List[str] = []

        self.log_id = manager.log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"atl_{self.log_id}"}

        self.msg_namespaces: str = ""
        self.msg_tools: str = ""

        self._init_namespaces()
        self._init_tools()

    def _init_namespaces(self):
        if settings.IS_PYTHON_TOOL_ENABLED:
            self.namespaces.append(AdapterToolNamespace.NATIVE_PYTHON.value)

        if settings.IS_BROWSER_TOOL_ENABLED:
            self.namespaces.append(AdapterToolNamespace.NATIVE_BROWSER.value)

        if self.manager.manager.params.tools:
            self.namespaces.append(AdapterToolNamespace.CUSTOM_DEVELOPER.value)

        self.msg_namespaces = "\n".join([i.replace(".", "") for i in self.namespaces])

    def _init_tools(self):
        for tool in self.manager.manager.params.tools or []:
            match tool:
                case AdapterFunctionToolResponses() | AdapterCustomToolResponses():
                    self.tools.append(tool.name)
                case AdapterFunctionToolChat():
                    self.tools.append(tool.function.name)

        if settings.IS_PYTHON_TOOL_ENABLED:
            self.tools.append(AdapterToolNamespace.NATIVE_PYTHON.value)

        if settings.IS_BROWSER_TOOL_ENABLED:
            self.tools.append(AdapterToolNamespace.NATIVE_BROWSER.value)

        self.msg_tools = "\n".join([i.replace(".", "") for i in self.tools])

    def _is_valid_namespace(self, recipient: str, state: Optional[str] = None) -> bool:
        namespace = [i for i in self.namespaces if recipient.startswith(i)]
        if not namespace:
            if state is not None:
                return False
            self.logger.warning(
                f"invalid tool call: invalid or malformed namespace @@{recipient}@@",
                extra=self.log_extra,
            )
            self.manager._add_recovery_message(
                "**Invalid output**: invalid or malformed namespace.\n\n"
                "(eg: functions.shell).\n"
                f"- valid namespaces:\n{self.msg_namespaces}\n\n"
                f"- valid tools:\n{self.msg_tools}\n\n"
                f"You are trying to call: `{recipient}`."
            )
            return False
        return True

    def _is_valid_tool(self, recipient: str, state: Optional[str] = None) -> bool:
        namespace = [i for i in self.namespaces if recipient.startswith(i)]
        tool = recipient.split(f"{namespace[0]}.")[-1]
        is_python = recipient.startswith("python")
        is_browser = recipient.startswith("browser")
        is_native_tool = is_python or is_browser
        # TODO: handle python and browser, namespaces will get fucked
        # but also need to patch original inputs to include native tools
        # since downstream in tool_plugin_responses we'll check for tools present in inputs
        if not is_native_tool and tool not in self.tools:
            if state is not None:
                return False
            self.logger.warning(
                f"invalid tool call: invalid or malformed tool name @@{recipient}@@",
                extra=self.log_extra,
            )
            self.manager._add_recovery_message(
                f"**Invalid output**: invalid or malformed tool name.\n\n"
                f"- valid namespaces:\n{self.msg_namespaces}\n\n"
                f"- valid tools:\n{self.msg_tools}\n\n"
                f"You are trying to call: `{recipient}`."
                f"**IMPORTANT**: python and browser tools also act as their own namespaces, when available. "
                f"This means you must NOT include the `functions` namespace when calling python or browser, "
                "eg only `python` to execute python code or `browser.open` to visit a web page."
            )
            return False
            self.manager.response_buffer
        return True

    def is_valid(self, recipient: Optional[str], state: Optional[str] = None) -> bool:
        if recipient is None:
            # skip logs and messages, it's a defensive check from other state
            if state is not None:
                return False
            self.logger.warning(
                "invalid tool call: missing recipient", extra=self.log_extra
            )
            self.manager._add_recovery_message(
                "**Invalid output**: missing recipient in tool call.\n\n"
                "Calls to these tools must go to the analysis channel: 'python', 'browser'.\n"
                "Calls to these tools must go to the commentary channel: 'functions'.\n"
                "Example: <channel>analysis to=python <constrain> code<message>code_input).\n"
                "Example: <channel>commentary to=functions.shell <constrain> json<message>tool_inputs).\n"
                "**Important**: <channel>, <constrain> and <message> are "
                "special tokens; do not use verbaim as in the example, "
                "instead use the correct tokens you have been trained with.\n\n"
                f"- valid namespaces:\n{self.msg_namespaces}\n\n"
                f"- valid tools:\n{self.msg_tools}\n\n"
                f"You tried calling: `{recipient}`."
            )
            return False

        if not self._is_valid_namespace(recipient, state):
            return False
        self.manager.response_buffer
        if not self._is_valid_tool(recipient, state):
            return False

        return True

    # TODO: native tools enabled by caller, not default / config; if default,
    # it may confuse assistant if it also has eg. a shell tool (codex), and it
    # will probably prioritize python over its native tools
    # TODO: here, and maybe also caller tools, enable strict tool enforcement,
    # eg only call shell, that gets to spec parity with openai?

    def _call_python_tool(self, code: str):
        import json

        session_id = self.manager.manager.log_id
        sandbox_handler = self.manager.manager.sandbox_handler
        sandbox = sandbox_handler.sandbox
        req = SandboxRequest(session_id=session_id, code=code)
        res = sandbox.run(req)
        text = f"stdout: {res.stdout}\n\nstderr: {res.stderr}"
        self.manager._update_state_with_tool_result(text, "python")
        self.manager.response_buffer

        x = 1


    async def _call_browser_tool(self):
        pass

    async def maybe_call_native_tool(self):
        if self.manager.parser_state != AdapterConversationState.NATIVE_TOOL_CALL:
            return

        messages = self.manager.parser.messages
        if not messages:
            return

        last_message = messages[-1]
        recipient = last_message.recipient

        if not recipient:
            return

        is_python = recipient == "python"
        is_browser = recipient.startswith("browser")

        if is_python:
            return self._call_python_tool(last_message.content[0].text)
        
        if is_browser:
            return self._call_browser_tool()