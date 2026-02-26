from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from openai_harmony import Message

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import get_prompt, random_uuid
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython
from burrito.types.conversation_inputs import ConversationToolParam
from burrito.types.enums import ConversationStateEnum, ToolNamespaceEnum

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


class ToolHandler:
    def __init__(
        self,
        manager: "StateHandler",
        python_tool: Optional[BurritoPython],
        browser_tool: Optional[BurritoBrowser],
    ):
        self.manager = manager
        self.namespaces: List[str] = []
        self.tool_names: List[str] = []
        self.tools: Dict[str, ConversationToolParam] = {}

        self.log_id = manager.log_id
        self.logger = FastAPILogger.get_logger(__name__)
        self.log_extra = {"log_id": self.log_id}

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
            self.namespaces.append(ToolNamespaceEnum.PYTHON.value)

        if self.browser_tool is not None:
            self.namespaces.append(ToolNamespaceEnum.BROWSER.value)

        if self.manager.manager.params.tools:
            self.namespaces.append(ToolNamespaceEnum.FUNCTIONS.value)

        self.msg_namespaces = "\n".join([i.replace(".", "") for i in self.namespaces])

    def _init_tools(self):
        tools = self.manager.conversation_inputs.tools or []
        self.tools = {i.name: i for i in tools}
        self.tool_names = [
            i.name
            for i in tools
            if i.name
            not in [
                ToolNamespaceEnum.PYTHON.value,
                ToolNamespaceEnum.BROWSER.value,
            ]
        ]
        self.msg_tools = "\n".join([i.replace(".", "") for i in self.tool_names])

    def patch_native_tool_recipient(self):
        if settings.ENFORCE_STRICT_TOOL_NAMESPACES:
            return

        messages = self.manager.conversation.messages
        if not messages:
            return

        tool_name = messages[-1].recipient
        if not tool_name:
            return

        is_python = self._is_python(tool_name)
        is_browser = self._is_browser(tool_name)
        if not is_python and not is_browser:
            return

        if "functions." not in tool_name:
            return

        # dirty hack for downstream events that look for strict tool name
        # in tool.process_arguments(last_message)
        messages[-1].recipient = tool_name.replace("functions.", "")
        return

    def get_tool_model_is_trying_to_call(
        self,
    ) -> Optional[Union[ConversationToolParam, BurritoBrowser, BurritoPython]]:
        current_recipient = self.manager.parser.current_recipient
        prev_recipient = None
        messages = self.manager.parser.messages  # rust view, maybe still in progress
        if messages:
            prev_recipient = messages[-1].recipient
        recipient = current_recipient or prev_recipient
        if not recipient:
            return

        tool_name = recipient

        if self._is_python(tool_name):
            return self.python_tool
        elif self._is_browser(tool_name):
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

    def _is_python(
        self, recipient: str, treat_functions_python_as_builtin: bool = True
    ) -> bool:
        _name = ToolNamespaceEnum.PYTHON.value
        if not settings.ENFORCE_STRICT_TOOL_NAMESPACES:
            return _name in recipient
        return (
            len(recipient) > 0
            and _name in self.tools
            and (
                recipient == _name
                or (
                    treat_functions_python_as_builtin
                    and recipient == f"functions.{_name}"
                )
            )
        )

    def _is_browser(
        self, recipient: str, treat_functions_browser_as_builtin: bool = True
    ) -> bool:
        _name = ToolNamespaceEnum.BROWSER.value
        if not settings.ENFORCE_STRICT_TOOL_NAMESPACES:
            return _name in recipient
        return (
            len(recipient) > 0
            and _name in self.tools
            and (
                recipient.startswith(f"{_name}")
                or (
                    treat_functions_browser_as_builtin
                    and recipient.startswith(f"functions.{_name}")
                )
            )
        )

    def _is_native_tool(self, recipient: str) -> bool:
        return self._is_python(recipient) or self._is_browser(recipient)

    def _is_valid_namespace(self, recipient: str, state: Optional[str] = None) -> bool:
        namespace = [i for i in self.namespaces if recipient.startswith(i)]
        if not namespace:
            if state is not None:
                return False

            if settings.DEBUG_TOOL_CALLS:
                self.logger.warning(
                    f"invalid tool call: bad namespace: `{recipient}`.",
                    extra=self.log_extra,
                )
            msg = get_prompt("sentinel_bad_namespace").format(
                recipient=recipient,
                valid_namespaces=self.msg_namespaces,
                valid_tools=self.msg_tools,
            )
            self.manager._add_recovery_message(msg)
            return False
        return True

    def _is_valid_tool(self, recipient: str, state: Optional[str] = None) -> bool:
        if self._is_native_tool(recipient):
            return True

        tool_name = recipient.split("functions.")[-1]
        tool = self.tools.get(tool_name)
        if not tool:
            if state is not None:
                return False
            if settings.DEBUG_TOOL_CALLS:
                self.logger.warning(
                    f"invalid tool call: bad tool `{recipient}`",
                    extra=self.log_extra,
                )
            msg = get_prompt("sentinel_bad_tool_name").format(
                recipient=recipient,
                valid_namespaces=self.msg_namespaces,
                valid_tools=self.msg_tools,
            )
            self.manager._add_recovery_message(msg)
            return False
        return True

    def is_valid(self, recipient: Optional[str], state: Optional[str] = None) -> bool:
        if recipient is None:
            # skip logs and messages, it's a defensive check from other state
            if state is not None:
                return False
            if settings.DEBUG_TOOL_CALLS:
                self.logger.warning(
                    "invalid tool call: missing recipient", extra=self.log_extra
                )
            msg = get_prompt("sentinel_tool_missing_recipient").format(
                recipient=recipient,
                valid_namespaces=self.msg_namespaces,
                valid_tools=self.msg_tools,
            )
            self.manager._add_recovery_message(msg)
            return False

        tool = self.get_tool_model_is_trying_to_call()
        if tool is not None and not settings.ENFORCE_STRICT_TOOL_NAMESPACES:
            return True

        if not self._is_valid_tool(recipient, state):
            return False

        if settings.ENFORCE_STRICT_TOOL_NAMESPACES and not self._is_valid_namespace(
            recipient, state
        ):
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
                    f"Calling `{t_name}` tool params `{t_params}.",
                    extra=self.log_extra,
                )
            else:
                if settings.DEBUG_TOOL_CALLS:
                    self.logger.debug(f"calling tool `{t_name}`.", extra=self.log_extra)

            tool_result = await self.run_tool(tool, message)
            tool_call = self.tool_calls[-1]
            call_id = tool_call["call_id"]
            self.tool_results[call_id] = tool_result[0].content[0].text  # type: ignore
            if settings.DEBUG_TOOL_OUTPUTS:
                self.logger.debug(
                    (
                        f"Tool result for `{t_name}` tool with params `{t_params}:"
                        f"{tool_result[0].content[0].text}"  # type: ignore
                    ),
                    extra=self.log_extra,
                )
        except Exception as e:
            if settings.DEBUG_TOOL_CALLS:
                log = f"**Error calling tool `{t_name}`**:{repr(e)}"
                self.logger.error(log, extra=self.log_extra)

            err = f"{repr(e)}"
            msg = get_prompt("sentinel_tool_call_error").format(
                tool_name=t_name, error_response=err
            )
            self.manager._add_recovery_message(msg)
            return self.manager._recover_state()

        await self.manager.transition_handler.transition(
            token=None, state=ConversationStateEnum.NATIVE_TOOL_DONE
        )
        self.manager._update_state_with_tool_result(tool_result)

    async def maybe_call_native_tool(self):
        if self.manager.parser_state != ConversationStateEnum.NATIVE_TOOL_CALL:
            return

        messages = self.manager.conversation.messages  # rust view
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
