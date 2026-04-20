import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from openai_harmony import Message

from burrito.common.config import settings
from burrito.common.logger import FastAPILogger
from burrito.common.utils import get_prompt, patch_agent_pip_install, random_uuid
from burrito.tools.browser.tool import BurritoBrowser
from burrito.tools.python.tool import BurritoPython
from burrito.types.conversation_enums import (
    ConversationChannel,
    ConversationState,
    ConversationToolNamespace,
)
from burrito.types.conversation_inputs import ConversationToolParam

if TYPE_CHECKING:
    from burrito.handlers.state_handler import StateHandler


class ToolHandler:
    def __init__(
        self,
        manager: "StateHandler",
        python_tool: Optional[Union[BurritoPython, str]],
        browser_tool: Optional[Union[BurritoBrowser, str]],
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

        self.current_call_id = ""
        self.current_call_buffer = ""

        self._init_namespaces()
        self._init_tools()

    def _init_namespaces(self):
        if self.python_tool is not None:
            self.namespaces.append(ConversationToolNamespace.PYTHON.value)

        if self.browser_tool is not None:
            self.namespaces.append(ConversationToolNamespace.BROWSER.value)

        if self.manager.manager.params.tools:
            self.namespaces.append(ConversationToolNamespace.FUNCTIONS.value)

        self.msg_namespaces = "\n".join([i.replace(".", "") for i in self.namespaces])

    def _init_tools(self):
        tools = self.manager.conversation_inputs.tools or []
        self.tools = {i.name: i for i in tools}
        self.tool_names = [
            i.name
            for i in tools
            if i.name
            not in [
                ConversationToolNamespace.PYTHON.value,
                ConversationToolNamespace.BROWSER.value,
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
        messages[-1].recipient = tool_name.replace("functions", "")
        return

    async def get_python_tool(self) -> Optional[BurritoPython]:
        state_handler = self.manager
        session_id = state_handler.log_id
        session_handler = state_handler.manager.session_handler
        kernel_manager = session_handler.kernel_handler

        # always check the cache as tool may have been evicted by
        # another session's LRU insertion or by idle timeout
        cached = session_handler.get_python_tool(session_id)
        if isinstance(cached, BurritoPython):  # != "init-on-use"
            self.python_tool = cached
            return self.python_tool

        # cache miss or sentinel: create a new tool and register it
        if self.python_tool is None:
            return None

        kernel_id = None
        conn_info = None
        if kernel_manager is not None:
            kernel_id = await kernel_manager.acquire_kernel()
            conn_info = await kernel_manager.get_connection_info(kernel_id)
        self.python_tool = BurritoPython(
            self.log_id,
            kernel_id=kernel_id,
            conn_info=conn_info,
            kernel_manager=kernel_manager,
        )
        session_handler.set_python_tool(session_id, self.python_tool)
        return self.python_tool

    def get_browser_tool(self) -> Optional[BurritoBrowser]:
        state_handler = self.manager
        session_id = state_handler.log_id
        session_handler = state_handler.manager.session_handler

        # always check the cache as tool may have been evicted by
        # another session's LRU insertion or by idle timeout
        cached = session_handler.get_browser_tool(session_id)
        if isinstance(cached, BurritoBrowser):
            self.browser_tool = cached
            return self.browser_tool

        # cache miss or sentinel: create a new tool and register it
        if self.browser_tool is None:
            return None
        self.browser_tool = BurritoBrowser(self.log_id)
        session_handler.set_browser_tool(session_id, self.browser_tool)
        return self.browser_tool

    async def get_tool_model_is_trying_to_call(
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
        tool_name = re.sub(r"^functions\.|<\|channel\|>.*$", "", recipient)
        if self._is_python(tool_name):
            return await self.get_python_tool()
        elif self._is_browser(tool_name):
            return self.get_browser_tool()
        else:
            return self.tools.get(tool_name)

    async def register_tool_call(self) -> Dict[str, Any]:
        tool = await self.get_tool_model_is_trying_to_call()
        if tool is None:
            raise ValueError("Expected a ConversationToolParam, but got `None`")
        call_id = f"call_{random_uuid()}"

        tool_type = {"python": "native_python", "browser": "native_browser"}.get(
            tool.name, "function"
        )
        self.tool_calls.append(
            {
                "index": len(self.tool_calls),
                "call_id": call_id,
                "tool": tool,
                "name": tool.name,
                "type": tool_type,
                "content": "",
            }
        )
        self.current_call_id = call_id
        return self.tool_calls[-1]

    def _is_python(
        self, recipient: str, treat_functions_python_as_builtin: bool = True
    ) -> bool:
        _name = ConversationToolNamespace.PYTHON.value
        _is_enabled = (
            settings.IS_PYTHON_TOOL_AVAILABLE or settings.IS_PYTHON_TOOL_ALWAYS_ENABLED
        )
        if not settings.ENFORCE_STRICT_TOOL_NAMESPACES:
            return _name in recipient and _is_enabled
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
            and _is_enabled
        )

    def _is_browser(
        self, recipient: str, treat_functions_browser_as_builtin: bool = True
    ) -> bool:
        _name = ConversationToolNamespace.BROWSER.value
        _is_enabled = (
            settings.IS_BROWSER_TOOL_AVAILABLE
            or settings.IS_BROWSER_TOOL_ALWAYS_ENABLED
        )
        if not settings.ENFORCE_STRICT_TOOL_NAMESPACES:
            return _name in recipient and _is_enabled
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
            and _is_enabled
        )

    def _is_native_tool(self, recipient: str) -> bool:
        return self._is_python(recipient) or self._is_browser(recipient)

    def _is_valid_tool_namespace(
        self, recipient: str, state: Optional[str] = None
    ) -> bool:
        namespace = [i for i in self.namespaces if recipient.startswith(i)]
        if not namespace:
            if state is not None:
                return False

            if settings.DEBUG_TOOL_CALLS or settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    f"invalid tool call: bad namespace: `{recipient}`.",
                    extra=self.log_extra,
                )
            msg = get_prompt("sentinel_bad_tool_namespace").format(
                recipient=recipient,
                valid_namespaces=self.msg_namespaces,
                valid_tools=self.msg_tools,
            )
            self.manager._add_recovery_message(msg)
            return False
        return True

    def _is_valid_tool_name(self, recipient: str, state: Optional[str] = None) -> bool:
        if recipient and not self.tools:
            if state is not None:
                return False
            if settings.DEBUG_TOOL_CALLS or settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    f"invalid tool call: bad tool name `{recipient}` [no tools]",
                    extra=self.log_extra,
                )
            msg = get_prompt("sentinel_bad_tool_inline_tools").format(
                recipient=recipient,
                valid_namespaces=self.msg_namespaces,
                valid_tools=self.msg_tools,
            )
            self.manager._add_recovery_message(msg)
            return False

        if self._is_native_tool(recipient):
            return True

        # we don't use self.get_tool_model_is_trying_to_call since we need a raw
        # check that can be fed to the model in case of no tool or bad format
        tool_name = recipient.split("functions.")[-1]
        tool_name = re.sub(r"<\|channel\|>.*$", "", tool_name)
        tool = self.tools.get(tool_name)

        if not tool:
            if state is not None:
                return False
            if settings.DEBUG_TOOL_CALLS or settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    f"invalid tool call: bad tool `(functions.){tool_name}`",
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

    async def is_valid(
        self, recipient: Optional[str], state: Optional[str] = None
    ) -> bool:
        tool = await self.get_tool_model_is_trying_to_call()
        if recipient is None or tool is None:
            # skip logs and messages, it's a defensive check from other state
            if state is not None:
                return False

            if recipient is None:
                msg = get_prompt("sentinel_tool_missing_recipient").format(
                    recipient=recipient,
                    valid_namespaces=self.msg_namespaces,
                    valid_tools=self.msg_tools,
                )
            else:
                msg = get_prompt("sentinel_bad_tool_name").format(
                    recipient=recipient,
                    valid_namespaces=self.msg_namespaces,
                    valid_tools=self.msg_tools,
                )
            if settings.DEBUG_TOOL_CALLS or settings.DEBUG_STATE_ERRORS:
                self.logger.warning(
                    "invalid tool call: missing or bad recipient", extra=self.log_extra
                )
            self.manager._add_recovery_message(msg)
            return False

        if not settings.ENFORCE_STRICT_TOOL_NAMESPACES:
            return True
        if not self._is_valid_tool_name(recipient, state):
            return False
        if not self._is_valid_tool_namespace(recipient, state):
            return False
        return True

    @staticmethod
    async def run_tool(
        tool: Union[BurritoPython, BurritoBrowser], message: Message
    ) -> List[Message]:
        results = []
        async for msg in tool.process(message):
            # sometimes assistant issues tool calls on analysis, but probably
            # trained to receive them on commentary; so we default here to guard
            msg.channel = ConversationChannel.COMMENTARY.value
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

            # self.manager.manager._stop_stream("await run_tool")
            tool_result = await self.run_tool(tool, message)
            result_text = tool_result[0].content[0].text  # type: ignore

            if isinstance(tool, BurritoPython):
                result_text = result_text.replace(
                    "Note: you may need to restart the kernel to use updated packages.",
                    "",
                )
            tool_call = self.tool_calls[-1]
            call_id = tool_call["call_id"]
            self.tool_results[call_id] = result_text
            if settings.DEBUG_TOOL_OUTPUTS:
                self.logger.debug(
                    (
                        f"Tool result for `{t_name}` tool with params `{t_params}:"
                        f"{result_text}"
                    ),
                    extra=self.log_extra,
                )
        except Exception as e:
            if settings.DEBUG_TOOL_CALLS or settings.DEBUG_STATE_ERRORS:
                log = f"**Error calling tool `{t_name}`**:{repr(e)}"
                self.logger.error(log, extra=self.log_extra)

            err = f"{repr(e)}"
            msg = get_prompt("sentinel_tool_call_error").format(
                tool_name=t_name, error_response=err
            )
            self.manager._add_recovery_message(msg)
            return self.manager._recover_state()

        await self.manager.transition_handler.transition(
            token=None, state=ConversationState.NATIVE_TOOL_DONE
        )
        self.manager.update_state_with_tool_result(tool_result)

    async def maybe_call_native_tool(self):
        if self.manager.parser_state != ConversationState.NATIVE_TOOL_CALL:
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
            tool = await self.get_python_tool()
            if tool is None:
                raise AssertionError("Python tool can not be None.")
            last_message.content[0].text = patch_agent_pip_install(  # type: ignore
                text=last_message.content[0].text  # type: ignore
            )
        elif self._is_browser(recipient):
            tool = self.get_browser_tool()
            if tool is None:
                raise AssertionError("Browser tool can not be None.")
            self.manager.manager.browser_tool_used = True
        else:
            return
        await self._call_native_tool(tool, last_message)

    async def _cleanup_browser(self):
        if not isinstance(self.browser_tool, BurritoBrowser):
            return

    async def _cleanup_python(self):
        if not isinstance(self.python_tool, BurritoPython):
            return

        tool = await self.get_python_tool()
        if not isinstance(tool, BurritoPython):
            return

        try:
            await tool._interrupt_jupyter_kernel()
            msg = "Interrupted kernel for session."
            self.logger.info(msg, extra=self.log_extra)
        except Exception as e:
            msg = f"Failed to interrupt kernel for session: {e}"
            self.logger.warning(msg, extra=self.log_extra)

    async def cleanup_tools(self):
        await self._cleanup_browser()
        await self._cleanup_python()
