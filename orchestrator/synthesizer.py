import json
import os
from typing import Any, Dict
import httpx
from prompt import get_synthesizer_system_prompt

class SynthesizerLLM:
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1"
        self.model = "gpt-4o"
        self.temperature = 0.3

    async def synthesize(self, goal: str, state: Dict[str, Any]) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": get_synthesizer_system_prompt()},
                {"role": "user", "content": f"Goal:\n{goal}\n\nState JSON:\n{json.dumps(state, indent=2)}"},
            ],
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=60)) as hc:
            r = await hc.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        return data["choices"][0]["message"]["content"].strip()
