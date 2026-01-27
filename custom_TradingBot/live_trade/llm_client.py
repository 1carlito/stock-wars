
import os
import requests
import time
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any

class LLMClient(ABC):
    @abstractmethod
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass

class ChutesClient(LLMClient):
    def __init__(self, api_key: str, model: str, api_url: str = "https://llm.chutes.ai/v1/chat/completions"):
        self.api_key = api_key
        self.model = model
        self.api_url = api_url

    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.1),
        }

        max_retries = kwargs.get("max_retries", 5)
        wait_time = 2.0

        for attempt in range(max_retries):
            try:
                response = requests.post(self.api_url, headers=headers, json=body, timeout=120)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 0
                if (status_code == 429 or 500 <= status_code < 600) and attempt < max_retries - 1:
                    time.sleep(wait_time)
                    wait_time *= 2
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    wait_time *= 2
                else:
                    raise
        raise Exception("Max retries exceeded")

class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str, api_url: str = "https://api.openai.com/v1/chat/completions"):
        self.api_key = api_key
        self.model = model
        self.api_url = api_url

    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.1),
        }

        max_retries = kwargs.get("max_retries", 5)
        wait_time = 2.0

        for attempt in range(max_retries):
            try:
                response = requests.post(self.api_url, headers=headers, json=body, timeout=120)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 0
                if (status_code == 429 or 500 <= status_code < 600) and attempt < max_retries - 1:
                    time.sleep(wait_time)
                    wait_time *= 2
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    wait_time *= 2
                else:
                    raise
        raise Exception("Max retries exceeded")

def get_llm_client(provider: str, api_key: str, model: str = None) -> LLMClient:
    provider = provider.lower()
    if provider == "openai":
         return OpenAIClient(api_key, model or "gpt-4o")
    elif provider == "chutes":
         return ChutesClient(api_key, model or "deepseek-ai/DeepSeek-V3.1-Terminus")
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
