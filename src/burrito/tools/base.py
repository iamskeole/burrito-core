import inspect
import json
from abc import ABC
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union, get_type_hints

def tool_action(func=None, *, name: str = None, description: str = None):
    """
    Decorator to mark a method as an exposed tool action.
    """
    def decorator(f):
        f._is_tool_action = True
        f._action_name = name or f.__name__
        f._action_description = description or (f.__doc__.strip() if f.__doc__ else "No description provided.")
        return f

    if func is None:
        return decorator
    return decorator(func)


class Tool(ABC):
    """
    Abstract base class for all tools.
    Provides automated JSON schema generation and execution dispatching.
    """

    def get_tool_definition(self) -> List[Dict[str, Any]]:
        """
        Generates a JSON schema for all methods decorated with @tool_action.
        """
        definitions = []
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(method, "_is_tool_action", False):
                definitions.append(self._generate_method_schema(method))
        return definitions

    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        """
        Dispatches execution to the appropriate @tool_action method.
        """
        # specialized dispatch for actions that might be named differently in the schema vs method name
        # defaulting to looking up by the _action_name attribute attached by the decorator
        
        target_method = None
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(method, "_is_tool_action", False) and getattr(method, "_action_name", "") == action:
                target_method = method
                break
        
        # fallback: try matching by exact method name if action name didn't match (though definition suggests strict mapping)
        if not target_method:
             # If the action string matches the method name directly (and it is an action)
            if hasattr(self, action):
                 method = getattr(self, action)
                 if getattr(method, "_is_tool_action", False):
                     target_method = method

        if not target_method:
             raise ValueError(f"Unknown action: '{action}'")

        # Bind arguments
        # This is a simple implementation; a more robust one would validate types against type hints.
        sig = inspect.signature(target_method)
        try:
            bound_args = sig.bind(**params)
            bound_args.apply_defaults()
        except TypeError as e:
             raise ValueError(f"Invalid parameters for action '{action}': {str(e)}")

        result = target_method(*bound_args.args, **bound_args.kwargs)
        
        if inspect.isawaitable(result):
            return await result
        
        return result


    def _generate_method_schema(self, method: Callable) -> Dict[str, Any]:
        name = getattr(method, "_action_name")
        description = getattr(method, "_action_description")
        
        sig = inspect.signature(method)
        type_hints = get_type_hints(method)
        
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            
            param_type = type_hints.get(param_name, str) # Default to string if unknown
            json_type = self._map_python_type_to_json(param_type)
            
            if isinstance(json_type, dict):
                prop_def = json_type
            else:
                prop_def = {"type": json_type}
            
            # Helper to extract description from docstring could be added here if we used a specific docstring format
            # For now, we keep it simple.
            
            # Enum handling
            # if hasattr(param_type, "__args__") ... (omitted for brevity, can add if needed)
            
            properties[param_name] = prop_def
            
            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

    def _map_python_type_to_json(self, py_type: Any) -> Any:
        origin = getattr(py_type, "__origin__", None)
        args = getattr(py_type, "__args__", [])

        if origin is Union:
            # Handle Optional (Union[T, None])
            non_none = [t for t in args if t is not type(None)]
            if len(non_none) == 1:
                return self._map_python_type_to_json(non_none[0])
            # Handle true Union
            return {"anyOf": [{"type": self._map_python_type_to_json(t)} for t in non_none]}

        if origin is dict:
            return "object"
        if origin is list:
            return "array"

        if py_type == str:
            return "string"
        elif py_type == int:
            return "integer"
        elif py_type == bool:
            return "boolean"
        elif py_type == float:
            return "number"
        elif py_type == dict or py_type == Dict:
            return "object"
        elif py_type == list or py_type == List:
            return "array"
        
        return "string"
