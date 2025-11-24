import inspect
import functools
from typing import Any, Callable, Optional

def ai_function(name: str, description: str):
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        # Store metadata for tool generation
        wrapper._ai_metadata = {
            "name": name,
            "description": description,
            "parameters": _infer_parameters(func)
        }
        return wrapper
    return decorator

def _infer_parameters(func: Callable) -> dict:
    """
    Simple introspection to generate JSON schema for parameters.
    Supports basic types and Pydantic Annotated fields.
    """
    sig = inspect.signature(func)
    properties = {}
    required = []
    
    for param_name, param in sig.parameters.items():
        if param_name == "self": 
            continue
            
        param_type = "string" # default
        description = ""
        
        # Handle Annotated types (Annotated[str, Field(description="...")])
        if hasattr(param.annotation, "__metadata__"):
            # Extract description from Field
            for meta in param.annotation.__metadata__:
                if hasattr(meta, "description"):
                    description = meta.description
            
            # Extract type (simplified)
            base_type = param.annotation.__origin__
            if base_type == int:
                param_type = "integer"
            elif base_type == bool:
                param_type = "boolean"
        elif param.annotation == int:
            param_type = "integer"
        elif param.annotation == bool:
            param_type = "boolean"
            
        properties[param_name] = {
            "type": param_type,
            "description": description
        }
        
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
            
    return {
        "type": "object",
        "properties": properties,
        "required": required
    }

# Dummy classes for compatibility if needed
class AgentRunContext:
    pass

class FunctionInvocationContext:
    pass

