from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL

class GroqClient:
    def __init__(self):
        # Initialize Groq client with the key from config
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = GROQ_MODEL

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """
        Non-streaming generation (used for Intent Detection).
        """
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.1,
                max_completion_tokens=1024,
                top_p=1,
                stream=False,
                stop=None
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"Groq API Error: {e}")
            return "BROWSING"

    def stream(self, prompt: str, system_prompt: str = ""):
        """
        Streaming generation (used for Chat Response).
        Matches the logic: chunk.choices[0].delta.content
        """
        try:
            stream = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.7, # Slightly higher for more natural chat
                max_completion_tokens=1024,
                top_p=1,
                stream=True,
                stop=None
            )

            for chunk in stream:
                # Safe access to delta content
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        except Exception as e:
            print(f"Groq Stream Error: {e}")
            yield "I am currently experiencing high traffic. Please try again."