
import unittest
from ReasoningAgent import ReasoningAgent

class TestToolParsing(unittest.TestCase):
    def setUp(self):
        # minimal init relying on defaults/mocking if needed
        # We only need to test _extract_tool_calls which is purely functional
        self.agent = ReasoningAgent(api_key_override="fake", use_mcp_client=False)

    def test_legacy_format(self):
        text = "Some text\nTOOL_CALL: get_price(symbol='AAPL')"
        calls = self.agent._extract_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['name'], 'get_price')
        self.assertEqual(calls[0]['arguments']['symbol'], 'AAPL')

    def test_python_block_format(self):
        text = """Here is my plan:
```python
# checking price
get_price(symbol='AAPL', date='2024-01-01')
get_news(limit=5)
```
"""
        calls = self.agent._extract_tool_calls(text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['name'], 'get_price')
        self.assertEqual(calls[0]['arguments']['symbol'], 'AAPL')
        self.assertEqual(calls[1]['name'], 'get_news')
        self.assertEqual(calls[1]['arguments']['limit'], 5)

if __name__ == '__main__':
    unittest.main()
