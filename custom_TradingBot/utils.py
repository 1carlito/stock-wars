"""
Utility functions for OpenBB MCP Server
"""

from typing import Any, Callable, Dict, Optional
from functools import wraps


def _convert_openbb_result(result: Any) -> Any:
    """Convert OpenBB OBBject result to dictionary / list format."""
    if hasattr(result, "results"):
        # OBBject has .results attribute
        if hasattr(result.results, "to_dict"):
            return result.results.to_dict()
        elif hasattr(result.results, "to_dataframe"):
            # For DataFrame results
            df = result.results.to_dataframe()
            return df.to_dict("records")
        elif isinstance(result.results, list):
            # List of Data objects
            return [
                item.model_dump() if hasattr(item, "model_dump") else dict(item)
                for item in result.results
            ]
        elif isinstance(result.results, dict):
            return result.results
        else:
            return {"data": str(result.results)}
    elif hasattr(result, "to_dict"):
        return result.to_dict()
    elif hasattr(result, "to_dataframe"):
        df = result.to_dataframe()
        return df.to_dict("records")
    elif isinstance(result, dict):
        return result
    else:
        return {"data": str(result)}


def format_tool_result(
    tool_name: str, data: Any = None, error: Optional[Exception] = None, **kwargs: Any
) -> Dict[str, Any]:
    """Format tool result with a consistent structure.

    All tools should return this basic schema:
      - tool_name: str
      - data: any JSON-serializable payload (when successful)
      - error: string message (when failed)

    Additional fields (e.g. `premium_required`) can be passed via kwargs.
    """
    result: Dict[str, Any] = {"tool_name": tool_name}
    if error is not None:
        result["error"] = str(error)
    else:
        # Normalize empty payloads to an empty list for convenience
        result["data"] = data if data is not None else []
    if kwargs:
        result.update(kwargs)
    return result


def handle_premium_error(
    tool_name: str, error: Exception, fallback_message: Optional[str] = None
) -> Dict[str, Any]:
    """Handle premium endpoint errors consistently.

    Some FMP / OpenBB endpoints require a premium subscription. When that
    happens, we want to return a friendly message instead of a raw 402 error.
    """
    error_str = str(error)
    if (
        "Premium" in error_str
        or "402" in error_str
        or "subscription" in error_str.lower()
    ):
        return format_tool_result(
            tool_name,
            data=[],
            error=None,
            message=(
                fallback_message
                or f"{tool_name} requires a premium subscription and is not available on this plan."
            ),
            premium_required=True,
        )
    return format_tool_result(tool_name, error=error)


def openbb_tool_wrapper(tool_name: str) -> Callable[[Callable[..., Any]], Callable[..., Dict[str, Any]]]:
    """Decorator to wrap OpenBB tool calls with consistent error handling.

    The wrapped function should return the *raw* OpenBB result (OBBject or similar).
    This decorator will:
      - Convert the result via `_convert_openbb_result`
      - Wrap it in `format_tool_result`
      - Catch exceptions and return a structured error payload
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Dict[str, Any]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            try:
                raw_result = func(*args, **kwargs)
                data = _convert_openbb_result(raw_result)
                return format_tool_result(tool_name, data=data)
            except Exception as e:  # noqa: BLE001 - we want to surface any tool error
                return format_tool_result(tool_name, error=e)

        return wrapper

    return decorator

