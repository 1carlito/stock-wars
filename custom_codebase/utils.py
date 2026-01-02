"""
Utility functions for OpenBB MCP Server
"""

def _convert_openbb_result(result):
    """Convert OpenBB OBBject result to dictionary format"""
    if hasattr(result, 'results'):
        # OBBject has .results attribute
        if hasattr(result.results, 'to_dict'):
            return result.results.to_dict()
        elif hasattr(result.results, 'to_dataframe'):
            # For DataFrame results
            df = result.results.to_dataframe()
            return df.to_dict('records')
        elif isinstance(result.results, list):
            # List of Data objects
            return [item.model_dump() if hasattr(item, 'model_dump') else dict(item) for item in result.results]
        elif isinstance(result.results, dict):
            return result.results
        else:
            return {"data": str(result.results)}
    elif hasattr(result, 'to_dict'):
        return result.to_dict()
    elif hasattr(result, 'to_dataframe'):
        df = result.to_dataframe()
        return df.to_dict('records')
    elif isinstance(result, dict):
        return result
    else:
        return {"data": str(result)}

