import sys
import os
import json
from types import ModuleType
from datetime import datetime

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Mocking openbb before import
mock_obb_module = ModuleType("openbb")
mock_obb = ModuleType("obb")
mock_equity = ModuleType("equity")
mock_price = ModuleType("price")
mock_technical = ModuleType("technical")

# Mock cache_manager
mock_cm_module = ModuleType("cache_manager")
class MockCacheManager:
    def __init__(self, *args, **kwargs): pass
    def get(self, key): return None
    def set(self, key, val): pass

mock_cm_module.CacheManager = MockCacheManager
sys.modules["cache_manager"] = mock_cm_module

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
             self.results.append({
                 "date": "2024-01-01", 
                 "close": 150.0,
                 "RSI_14_CLOSE": 55.5 # Tricky key
             })
        def model_dump(self): return {"data": self.results}
    return Res()

def mock_ema(*args, **kwargs):
    class Res:
        results = []
        def __init__(self):
             self.results.append({
                 "date": "2024-01-01", 
                 "EMA_50": 145.0 # Tricky key
             })
        def model_dump(self): return {"data": self.results}
    return Res()

# Stitch mocks together
mock_price.historical = mock_historical
mock_equity.price = mock_price
mock_obb.equity = mock_equity

mock_technical.rsi = mock_rsi
mock_technical.ema = mock_ema
mock_obb.technical = mock_technical

mock_obb_module.obb = mock_obb
sys.modules["openbb"] = mock_obb_module

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
    
    print("\n--- Testing calculate_rsi (Found key: RSI_14_CLOSE) ---")
    if "calculate_rsi" in mcp.tools:
        # Call with NO dates to test defaults
        print("Calling calculate_rsi without dates...")
        try:
            result = mcp.tools["calculate_rsi"](symbol="AAPL")
            print("Result received.")
            
            # Check for wrapper dict
            data = result
            if isinstance(result, dict) and "data" in result:
                data = result["data"]
            
            if isinstance(data, list) and len(data) > 0:
                print(f"✅ Data is list. Item: {data[0]}")
                if data[0].get("rsi") == 55.5:       
                    print("✅ Fuzzy extraction worked for RSI")
                else: 
                    print(f"❌ Fuzzy extraction failed. RSI: {data[0].get('rsi')}")
            else:
                 print(f"❌ Unexpected result format: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

    print("\n--- Testing calculate_ema (Found key: EMA_50) ---")
    if "calculate_ema" in mcp.tools:
        print("Calling calculate_ema...")
        try:
            result = mcp.tools["calculate_ema"](symbol="AAPL") 
            
            # Check for wrapper dict
            data = result
            if isinstance(result, dict) and "data" in result:
                data = result["data"]

            if isinstance(data, list) and len(data) > 0:
                print(f"✅ Data is list. Item: {data[0]}")
                if data[0].get("ema") == 145.0:       
                    print("✅ Fuzzy extraction worked for EMA")
                else: 
                    print(f"❌ Fuzzy extraction failed. EMA: {data[0].get('ema')}")
            else:
                 print(f"❌ Unexpected result format: {result}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

except Exception as e:
    print(f"❌ Script Error: {e}")
    import traceback
    traceback.print_exc()
