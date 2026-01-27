import sys
import os
import json
from types import ModuleType

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Mocking openbb before import
mock_obb_module = ModuleType("openbb")
mock_obb = ModuleType("obb")
mock_equity = ModuleType("equity")
mock_price = ModuleType("price")
mock_technical = ModuleType("technical")

# Define mock functions
def mock_historical(*args, **kwargs):
    class Res:
        results = [{"date": "2024-01-01", "close": 150.0}]
        def to_dataframe(self):
             import pandas as pd
             return pd.DataFrame(self.results)
    return Res()

def mock_rsi(*args, **kwargs):
    class Res:
        results = []
        def __init__(self):
            for i in range(2):
                self.results.append({
                    "date": "2024-01-01", 
                    "close": 150.0,
                    "RSI_14_": 50.0 + i
                })
        def model_dump(self):
            return {"data": self.results} # Not really used since we iterate manually
            
    return Res()

# Stitch mocks together
mock_price.historical = mock_historical
mock_equity.price = mock_price
mock_obb.equity = mock_equity

mock_technical.rsi = mock_rsi
mock_obb.technical = mock_technical

mock_obb_module.obb = mock_obb
sys.modules["openbb"] = mock_obb_module

# Mock cache_manager to avoid disk cache issues with local classes
mock_cm_module = ModuleType("cache_manager")
class MockCacheManager:
    def __init__(self, *args, **kwargs): pass
    def get(self, key): return None
    def set(self, key, val): pass

mock_cm_module.CacheManager = MockCacheManager
sys.modules["cache_manager"] = mock_cm_module

# Now import
from Tools import openbb_technical_tools

# Instantiate Mock MCP
class MockMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, name=None):
        def decorator(func):
            self.tools[name] = func
            return func
        return decorator

try:
    mcp = MockMCP()
    openbb_technical_tools.register_openbb_technical_tools(mcp)
    
    print("\n--- Testing calculate_rsi ---")
    if "calculate_rsi" in mcp.tools:
        # Call the tool
        # Since we mocked openbb, we can call it without errors hopefully!
        print("Calling calculate_rsi...")
        try:
            result = mcp.tools["calculate_rsi"](symbol="AAPL", start_date="2024-01-01", end_date="2024-01-10")
            print("Result received.")
            # Check structure
            # Expecting: {'tool_name': 'calculate_rsi', 'data': [{'date': '2024-01-01', 'rsi': ..., ...}]}
            
            print(f"Result keys: {result.keys()}")
            
            data = result.get("data")
            if isinstance(data, list):
                print(f"✅ Data is list (len={len(data)})")
                if len(data) > 0:
                    print(f"Sample item keys: {data[0].keys()}")
                    if "rsi" in data[0]:
                        print("✅ Item has 'rsi'")
                    else:
                        print(f"❌ Item missing 'rsi': {data[0]}")
            elif isinstance(data, dict):
                print("❌ Data is dict (Double wrapping detected? or empty?)")
                print(data)
            else:
                print(f"❌ Data is unknown type: {type(data)}")
                if "error" in result:
                    print(f"Error message: {result['error']}")
                
        except Exception as e:
            print(f"❌ Error during execution: {e}")
            import traceback
            traceback.print_exc()
            
    else:
        print("❌ calculate_rsi not registered")

except Exception as e:
    print(f"❌ Script Error: {e}")
    import traceback
    traceback.print_exc()
