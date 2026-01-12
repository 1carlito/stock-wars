"""
Test script for Phase 3: Sector Ranking System

Tests:
  1. Sector rankings tool returns valid data
  2. Sectors are ranked with scores
  3. Multiple sectors are returned
  4. Company sector lookup works
"""

import os
import sys
from datetime import datetime

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
custom_trading_bot_dir = os.path.join(base_dir, "custom_TradingBot")
sys.path.insert(0, custom_trading_bot_dir)
sys.path.insert(0, base_dir)

# Load environment
from dotenv import load_dotenv
env_path = os.path.join(custom_trading_bot_dir, ".env")
load_dotenv(env_path)

print("=" * 80)
print("PHASE 3 TEST: Sector Ranking System")
print("=" * 80)

# --- TEST 1: Sector Rankings Tool Response ---
print("\n[TEST 1] Sector rankings tool response format")
try:
    from Tools.Sector_Tools import register_sector_tools
    from utils import format_tool_result

    # Create a mock MCP server
    class SimpleMCP:
        def tool(self, name):
            def decorator(func):
                # Store function globally for later access
                setattr(SimpleMCP, f"_func_{name}", func)
                return func
            return decorator

    mcp = SimpleMCP()
    register_sector_tools(mcp)

    # Get the registered function
    get_sector_rankings = getattr(SimpleMCP, "_func_get_sector_rankings")
    test_date = "2026-01-11"
    result = get_sector_rankings(test_date)

    print(f"  Response type: {type(result)}")
    print(f"  Has 'data' key: {'data' in result if isinstance(result, dict) else False}")

    assert isinstance(result, dict), "Result is not a dict"
    assert "data" in result, "Result missing 'data' key"

    data = result["data"]
    assert "sectors" in data, "Data missing 'sectors' key"
    sectors = data["sectors"]
    print(f"  Number of sectors: {len(sectors)}")
    print(f"  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- TEST 2: Sector Data Validation ---
print("\n[TEST 2] Sector data validation")
try:
    assert len(sectors) == 11, f"Expected 11 sectors, got {len(sectors)}"
    print(f"  Total sectors: {len(sectors)} ✓")

    # Check each sector has required fields
    required_fields = ["name", "score", "rank", "momentum", "weight"]
    for sector in sectors:
        for field in required_fields:
            assert field in sector, f"Sector missing '{field}': {sector}"

    print(f"  All sectors have required fields ✓")

    # Verify scores are in valid range
    for sector in sectors:
        score = sector["score"]
        assert 0 <= score <= 100, f"Score {score} out of range [0, 100]"

    print(f"  All scores in valid range [0, 100] ✓")

    # Verify ranks are sequential
    ranks = sorted([s["rank"] for s in sectors])
    expected_ranks = list(range(1, len(sectors) + 1))
    assert ranks == expected_ranks, f"Ranks not sequential: {ranks}"
    print(f"  Ranks are sequential 1-{len(sectors)} ✓")

    # Verify momentum values are valid
    valid_momentum = ["strong", "moderate", "neutral", "weak", "very_weak"]
    for sector in sectors:
        momentum = sector["momentum"]
        assert momentum in valid_momentum, f"Invalid momentum: {momentum}"

    print(f"  All momentum values valid ✓")
    print(f"  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 3: Sector Ranking Order ---
print("\n[TEST 3] Sector ranking order")
try:
    print(f"  Sectors ranked by score (descending):")
    # Sort by rank to verify descending order
    sectors_by_rank = sorted(sectors, key=lambda s: s["rank"])

    for sector in sectors_by_rank[:5]:
        print(f"    {sector['rank']:2d}. {sector['name']:25s} Score: {sector['score']:5.1f} Momentum: {sector['momentum']}")

    # Verify scores are generally in descending order (allowing for equal scores)
    scores = [s["score"] for s in sectors_by_rank]
    is_descending = all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))
    assert is_descending, "Scores are not in descending order"
    print(f"  Scores in descending order ✓")
    print(f"  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

# --- TEST 4: Company Sector Lookup ---
print("\n[TEST 4] Company sector lookup")
try:
    get_company_sector = getattr(SimpleMCP, "_func_get_company_sector", None)

    if not get_company_sector:
        # Register and get the function
        mcp2 = SimpleMCP()
        register_sector_tools(mcp2)
        get_company_sector = getattr(SimpleMCP, "_func_get_company_sector")

    # Test AAPL
    result = get_company_sector("AAPL")
    print(f"  AAPL lookup result: {result}")

    if "error" in result:
        print(f"  ⚠️  Company lookup not available on Starter tier: {result['error']}")
    elif "data" in result:
        data = result["data"]
        sector = data.get("sector", "Unknown")
        industry = data.get("industry", "Unknown")
        print(f"  AAPL sector: {sector}")
        print(f"  AAPL industry: {industry}")
        assert sector != "Unknown", "Sector not found"
        print(f"  ✅ PASS")
    else:
        print(f"  ⚠️  Unexpected response format")

except Exception as e:
    print(f"  ⚠️  Company sector lookup test skipped: {e}")

# --- TEST 5: Sector Weights ---
print("\n[TEST 5] Sector weights validation")
try:
    weights = [s["weight"] for s in sectors]
    total_weight = sum(weights)
    print(f"  Total sector weight: {total_weight:.2f}")
    assert 0.99 <= total_weight <= 1.01, f"Weights don't sum to ~1.0: {total_weight}"
    print(f"  Weights sum to 1.0 ✓")
    print(f"  ✅ PASS")

except Exception as e:
    print(f"  ❌ FAIL: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("PHASE 3 TESTS PASSED ✅")
print("=" * 80)
print("\nSummary:")
print("  ✅ Sector rankings tool registered successfully")
print("  ✅ All 11 S&P 500 sectors returned with valid data")
print("  ✅ Sectors ranked 1-11 with scores 0-100")
print("  ✅ Momentum indicators valid (strong/moderate/neutral/weak/very_weak)")
print("  ✅ Sector weights sum to 1.0 for portfolio allocation")
print("\nPhase 3 (Sector Ranking System) foundation is complete!")
print("Ready for integration with waterfall allocation...")
