from typing import TYPE_CHECKING, List, Optional, Union, Dict, Any

from gpt_oss.tools.python_docker.docker_tool import PythonTool

from burrito.tools.browser.tool import BurritoBrowser

from openai_harmony import Message

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.types.adapter import AdapterConversationState
from burrito.types.adapter.adapter_conversation_inputs import (
    AdapterConversationInputTool,
)
from burrito.types.adapter.adapter_tool_namespace import AdapterToolNamespace

from burrito.common.utils import random_uuid

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
        self.tool_names: List[str] = []
        self.tools: Dict[str, AdapterConversationInputTool] = {}

        self.log_id = manager.log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"atl_{self.log_id}"}

        self.msg_namespaces: str = ""
        self.msg_tools: str = ""

        self.tool_calls: list[Dict[str, Any]] = []

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
        tools = self.manager.conversation_inputs.tools or []
        self.tools = {i.name: i for i in tools}
        self.tool_names = [i.name for i in tools]

        self.msg_tools = "\n".join([i.replace(".", "") for i in self.tool_names])

    def get_tool_model_is_trying_to_call(self) -> AdapterConversationInputTool | None:
        recipient = self.manager.parser.current_recipient
        if not recipient:
            return

        tool_name = recipient

        if tool_name == AdapterToolNamespace.NATIVE_PYTHON.value:
            pass
        elif recipient.startswith(AdapterToolNamespace.NATIVE_BROWSER.value + "."):
            pass
        else:
            # see if we have a tool with a namespace prefix
            try_split = recipient.split(".")
            # if no prefix, just return tool name
            if try_split and len(try_split) > 1:
                tool_name = try_split[1]

        return self.tools.get(tool_name)

    def register_tool_call(self) -> Dict[str, Any]:
        tool = self.get_tool_model_is_trying_to_call()
        assert tool is not None, (
            "Expected a AdapterConversationInputTool, but got `None`"
        )

        call_id = f"call_{random_uuid()}"
        self.tool_calls.append(
            {"index": len(self.tool_calls), "call_id": call_id, "tool": tool}
        )
        return self.tool_calls[-1]

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
        if not is_native_tool and tool not in self.tool_names:
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

        if not self._is_valid_tool(recipient, state):
            return False

        return True

    # TODO: native tools enabled by caller, not default / config; if default,
    # it may confuse assistant if it also has eg. a shell tool (codex), and it
    # will probably prioritize python over its native tools
    # TODO: here, and maybe also caller tools, enable strict tool enforcement,
    # eg only call shell, that gets to spec parity with openai?

    @staticmethod
    async def run_tool(
        tool: Union[PythonTool, BurritoBrowser], message: Message
    ) -> List[Message]:
        results = []
        async for msg in tool.process(message):
            results.append(msg)

        return results

    async def _call_native_tool(
        self, tool: Union[PythonTool, BurritoBrowser], message: Message
    ):
        try:
            # print(f"Calling tool: {tool.name} with params: {message.content[0].text}")
            tool_result = await self.run_tool(tool, message)
            # txt = tool_result[0].content[0].text
            # from burrito.common.utils import simple_markdown_renderer
            # print(simple_markdown_renderer(txt))
        except Exception as e:
            msg = f"**Error calling {tool.name} tool**: {repr(e)}"
            self.logger.warning(msg, extra=self.log_extra)
            self.manager._add_recovery_message(msg)
            return self.manager._recover_state()
        self.manager._update_state_with_tool_result(tool_result)

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

        is_python = recipient == "python" or recipient.startswith("functions.python")
        is_browser = recipient.startswith("browser.")

        tool = None
        if is_python:
            tool = self.manager.manager.python_tool
        if is_browser:
            tool = self.manager.manager.browser_tool
            self.manager.manager.browser_tool_used = True

        if tool is None:
            return

        await self._call_native_tool(tool, last_message)
