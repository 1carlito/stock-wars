import sys
import os
import logging

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
# live_trade is a subdirectory of custom_TradingBot
sys.path.append(os.path.join(current_dir, "live_trade"))
# custom_TradingBot is the current dir
sys.path.append(current_dir)

# Reset logging to avoid clutter
logging.basicConfig(level=logging.CRITICAL)

from ReasoningAgent import ReasoningAgent

def test_prompt_filtering():
    print("Initializing ReasoningAgent for testing...")
    # Initialize with dummy values
    agent = ReasoningAgent(api_key_override="test")
    
    # Mock available tools - specific restricted set
    agent.available_tools = ["calculate_rsi", "get_price_history"] 
    print(f"Mocked available tools: {agent.available_tools}")
    
    # Request 'technical_indicators' category which usually has many tools (bbands, macd, etc.)
    # We expect ONLY calculate_rsi (and maybe get_price_history if it was in technical, which it isn't usually)
    print("Building system prompt with category 'technical_indicators'...")
    try:
        prompt = agent._build_system_prompt(selected_categories=["technical_indicators"])
    except Exception as e:
        print(f"❌ Error building prompt: {e}")
        return

    # Extract tools section
    try:
        if "You have access to the following tools:" in prompt:
            tools_section = prompt.split("You have access to the following tools:")[1].split("\n\n")[0]
        else:
             tools_section = prompt # Fallback
             
        print("\n--- Generated Tools List ---")
        print(tools_section.strip())
        print("----------------------------")
        
        # Validation
        failures = []
        if "calculate_bbands" in tools_section:
            failures.append("'calculate_bbands' leaked into prompt (should be filtered)")
        
        if "calculate_rsi" not in tools_section:
             failures.append("'calculate_rsi' missing from prompt (should be present)")
             
        if not failures:
            print("\n✅ SUCCESS: Prompt filtering logic is working correctly!")
        else:
            print("\n❌ FAILURE: Prompt filtering failed:")
            for f in failures:
                print(f"  - {f}")
                
    except Exception as e:
        print(f"❌ Verification Logic Error: {e}")

if __name__ == "__main__":
    test_prompt_filtering()
