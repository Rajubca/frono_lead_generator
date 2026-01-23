import requests
from typing import Generator
from config import LLAMA_API_URL, LLAMA_MODEL, LLAMA_TIMEOUT
import json

DEFAULT_SYSTEM_PROMPT = (
    "You are Frono’s official AI assistant.\n"
    "Rules:\n"
    "- Do NOT assume product categories, brands, or services.\n"
    "- Do NOT invent features about the website.\n"
    "- Only use information explicitly provided in context.\n"
    "- If information is missing, ask a clarifying question.\n"
    "- Be concise and helpful."
)


class LLaMAClient:
    def __init__(self):
        self.url = LLAMA_API_URL
        self.model = LLAMA_MODEL

    def _build_payload(self, prompt: str, system_prompt: str, stream: bool):
        return {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt or DEFAULT_SYSTEM_PROMPT,
            "stream": stream,
            "options": {
                "num_predict": 300,       # <--- CHANGED from 120 to 300
                "temperature": 0.3,       # Slightly higher for better flow
                "top_p": 0.9,
                "repeat_penalty": 1.1
            }
        }
    # -----------------------------
    # STANDARD (NON-STREAMING)
    # -----------------------------
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        payload = self._build_payload(prompt, system_prompt, stream=False)

        try:
            response = requests.post(
                self.url,
                json=payload,
                timeout=LLAMA_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()

        except requests.exceptions.Timeout:
            return "Sorry — that took longer than expected. Please try again."

        except requests.exceptions.RequestException:
            return "I'm temporarily unavailable. Please try again later."

    # -----------------------------
    # STREAMING (STEP 9 READY)
    # -----------------------------
    import json
    import requests
    from typing import Generator

    def stream(self, prompt: str, system_prompt: str = ""):
        payload = self._build_payload(prompt, system_prompt, stream=True)

        with requests.post(
            self.url,
            json=payload,
            stream=True,
            timeout=LLAMA_TIMEOUT
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "response" in data:
                    yield data["response"]

                if data.get("done") is True:
                    break
