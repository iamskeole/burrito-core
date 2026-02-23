from typing import TYPE_CHECKING, List, Optional, Union, Dict, Any


from openai_harmony import Message

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.types.adapter import AdapterConversationState
from burrito.types.adapter.adapter_conversation_inputs import (
    AdapterConversationInputTool,
)
from burrito.types.adapter.adapter_tool_namespace import AdapterToolNamespace

from burrito.common.utils import random_uuid

from burrito.tools.python.tool import BurritoPython
from burrito.tools.browser.tool import BurritoBrowser

if TYPE_CHECKING:
    from burrito.handlers.state_handler import AdapterStateHandler


class ToolHandler:
    def __init__(
        self,
        manager: "AdapterStateHandler",
        python_tool: Optional[BurritoPython],
        browser_tool: Optional[BurritoBrowser],
    ):
        self.manager = manager
        self.namespaces: List[str] = []
        self.tool_names: List[str] = []
        self.tools: Dict[str, AdapterConversationInputTool] = {}

        self.log_id = manager.log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": f"{self.log_id} | {__name__}"}

        self.msg_namespaces: str = ""
        self.msg_tools: str = ""

        self.tool_calls: list[Dict[str, Any]] = []
        self.tool_results: Dict[str, Any] = {}

        self.python_tool = python_tool
        self.browser_tool = browser_tool

        self._init_namespaces()
        self._init_tools()

    def _init_namespaces(self):
        if self.python_tool is not None:
            self.namespaces.append(AdapterToolNamespace.NATIVE_PYTHON.value)

        if self.browser_tool is not None:
            self.namespaces.append(AdapterToolNamespace.NATIVE_BROWSER.value)

        if self.manager.manager.params.tools:
            self.namespaces.append(AdapterToolNamespace.CUSTOM_DEVELOPER.value)

        self.msg_namespaces = "\n".join([i.replace(".", "") for i in self.namespaces])

    def _init_tools(self):
        tools = self.manager.conversation_inputs.tools or []
        self.tools = {i.name: i for i in tools}
        self.tool_names = [
            i.name
            for i in tools
            if i.name
            not in [
                AdapterToolNamespace.NATIVE_PYTHON.value,
                AdapterToolNamespace.NATIVE_BROWSER.value,
            ]
        ]
        self.msg_tools = "\n".join([i.replace(".", "") for i in self.tool_names])

    def get_tool_model_is_trying_to_call(
        self,
    ) -> Optional[Union[AdapterConversationInputTool, BurritoBrowser, BurritoPython]]:
        current_recipient = self.manager.parser.current_recipient
        prev_recipient = None
        parser_messages = self.manager.parser.messages
        if parser_messages:
            prev_recipient = parser_messages[-1].recipient
        recipient = current_recipient or prev_recipient
        if not recipient:
            return

        tool_name = recipient

        if tool_name == AdapterToolNamespace.NATIVE_PYTHON.value:
            return self.python_tool
        elif recipient.startswith(AdapterToolNamespace.NATIVE_BROWSER.value + "."):
            return self.browser_tool
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
            {
                "index": len(self.tool_calls),
                "call_id": call_id,
                "tool": tool,
            }
        )
        return self.tool_calls[-1]

    def _is_valid_namespace(self, recipient: str, state: Optional[str] = None) -> bool:
        namespace = [i for i in self.namespaces if recipient.startswith(i)]
        if not namespace:
            if state is not None:
                return False
            self.logger.warning(
                f"invalid tool call: invalid or malformed namespace: `{recipient}`.",
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

    def _is_python(
        self, recipient: str, treat_functions_python_as_builtin: bool = True
    ) -> bool:
        _name = AdapterToolNamespace.NATIVE_PYTHON.value
        return (
            len(recipient) > 0
            and _name in self.tools
            and (
                recipient.startswith(_name)
                or (
                    treat_functions_python_as_builtin
                    and recipient == f"functions.{_name}"
                )
            )
        )

    def _is_browser(self, recipient: str) -> bool:
        _name = AdapterToolNamespace.NATIVE_BROWSER.value
        return (
            len(recipient) > 0
            and _name in self.tools
            and recipient.startswith(f"{_name}")
        )

    def _is_native_tool(self, recipient: str) -> bool:
        return self._is_python(recipient) or self._is_browser(recipient)

    def _is_valid_tool(self, recipient: str, state: Optional[str] = None) -> bool:
        if self._is_native_tool(recipient):
            return True

        tool_name = recipient.split("functions.")[-1]
        tool = self.tools.get(tool_name)
        if not tool:
            if state is not None:
                return False
            self.logger.warning(
                f"invalid tool call: invalid or malformed tool name `{recipient}`",
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

    @staticmethod
    async def run_tool(
        tool: Union[BurritoPython, BurritoBrowser], message: Message
    ) -> List[Message]:
        results = []
        async for msg in tool.process(message):
            results.append(msg)
        return results

    async def _call_native_tool(
        self, tool: Union[BurritoPython, BurritoBrowser], message: Message
    ):
        t_name, t_params = message.recipient, message.content[0].text  # type: ignore
        try:
            if settings.DEBUG_TOOL_INPUTS:
                self.logger.debug(
                    f"Calling `{t_name}` tool params `{t_params}.", extra=self.log_extra
                )
            else:
                self.logger.debug(f"calling tool `{t_name}`.", extra=self.log_extra)

            tool_result = await self.run_tool(tool, message)
            tool_call = self.tool_calls[-1]
            call_id = tool_call["call_id"]
            self.tool_results[call_id] = tool_result
            if settings.DEBUG_TOOL_OUTPUTS:
                self.logger.debug(
                    (
                        f"Tool result for `{t_name}` tool with params `{t_params}:"
                        f"{tool_result[0].content[0].text}"  # type: ignore
                    ),
                    extra=self.log_extra,
                )
        except Exception as e:
            msg = f"**Error calling tool `{t_name}`**:{repr(e)}"
            self.logger.error(msg, extra=self.log_extra)
            self.manager._add_recovery_message(msg)
            return self.manager._recover_state()

        await self.manager.transition_handler.transition(
            token=None, state=AdapterConversationState.NATIVE_TOOL_DONE
        )
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

        tool = None
        if self._is_python(recipient):
            tool = self.python_tool
        if self._is_browser(recipient):
            tool = self.browser_tool
            self.manager.manager.browser_tool_used = True
        if tool is None:
            return
        await self._call_native_tool(tool, last_message)
