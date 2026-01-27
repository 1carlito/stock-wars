
import unittest
from unittest.mock import patch, MagicMock
from llm_client import get_llm_client, ChutesClient, OpenAIClient

class TestLLMClient(unittest.TestCase):
    def test_factory_chutes(self):
        client = get_llm_client("chutes", "fake-key")
        self.assertIsInstance(client, ChutesClient)
        self.assertEqual(client.model, "deepseek-ai/DeepSeek-V3.1-Terminus")

    def test_factory_openai(self):
        client = get_llm_client("openai", "fake-key")
        self.assertIsInstance(client, OpenAIClient)
        self.assertEqual(client.model, "gpt-4o")

    @patch('requests.post')
    def test_chutes_call(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hello from Chutes"}}]}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = ChutesClient("fake-key", "model-v1")
        response = client.chat_completion([{"role": "user", "content": "Hi"}])
        
        self.assertEqual(response, "Hello from Chutes")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['model'], "model-v1")

    @patch('requests.post')
    def test_openai_call(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hello from OpenAI"}}]}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = OpenAIClient("fake-key", "gpt-4")
        response = client.chat_completion([{"role": "user", "content": "Hi"}])
        
        self.assertEqual(response, "Hello from OpenAI")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['model'], "gpt-4")

if __name__ == '__main__':
    unittest.main()
