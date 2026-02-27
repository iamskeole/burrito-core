from enum import Enum


class ConversationChannel(Enum):
    ANALYSIS = "analysis"
    COMMENTARY = "commentary"
    FINAL = "final"


class ConversationState(str, Enum):
    INITIAL = "initial"
    CREATED = "created"
    IN_PROGRESS = "in_progress"

    REASONING = "reasoning"
    REASONING_END = "reasoning_end"

    NATIVE_TOOL_INPUT_START = "native_tool_input_start"
    NATIVE_TOOL_INPUT = "native_tool_input"
    NATIVE_TOOL_CALL = "native_tool_call"
    NATIVE_TOOL_DONE = "native_tool_done"

    TOOL_INPUT_START = "tool_input_start"
    TOOL_INPUT = "tool_input"
    TOOL_CALL = "tool_call"

    OUTPUT_TEXT = "output_text"
    COMPLETED = "completed"
    TRANSITION = "transition"
    PREAMBLE = "preamble"
    ERROR = "error"


class ConversationReasoningEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConversationReasoningSummary(str, Enum):
    AUTO = "auto"
    CONCISE = "concise"
    DETAILED = "detailed"


class ConversationToolNamespace(Enum):
    PYTHON = "python"
    BROWSER = "browser"
    FUNCTIONS = "functions"


class ConversationToolType(Enum):
    PYTHON = "python"
    BROWSER = "browser"
    FUNCTION = "function"
    CUSTOM = "custom"
