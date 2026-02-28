from pydantic import BaseModel


class ConversationUsage(BaseModel):
    n_input: int
    n_reasoning: int
    n_preamble: int
    n_native_tool_input: int
    n_caller_tool_input: int
    n_output_text: int
    n_completion: int
    n_total: int
    n_cached: int
