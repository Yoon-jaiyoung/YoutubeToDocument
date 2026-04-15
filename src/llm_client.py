import os


LOCAL_BASE_URL = "http://localhost:8080/v1"
LOCAL_DEFAULT_MODEL = "mlx-community/gemma-4-e4b-it-4bit"


class LLMClient:
    def __init__(self, model_type: str, local_model: str = LOCAL_DEFAULT_MODEL):
        self.model_type = model_type
        self.local_model = local_model
        self._client = None
        self._model_name = None
        self._setup()

    def _setup(self):
        if self.model_type == "local":
            from openai import OpenAI
            self._client = OpenAI(base_url=LOCAL_BASE_URL, api_key="none")
            self._model_name = self.local_model

        elif self.model_type == "claude":
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
            self._client = anthropic.Anthropic(api_key=api_key)
            self._model_name = "claude-sonnet-4-6"

        elif self.model_type == "gpt":
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
            self._client = OpenAI(api_key=api_key)
            self._model_name = "gpt-4o"

        elif self.model_type == "gemini":
            import google.generativeai as genai
            api_key = os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY 환경변수가 설정되지 않았습니다.")
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel("gemini-1.5-pro")
            self._model_name = "gemini-1.5-pro"

        else:
            raise ValueError(f"지원하지 않는 모델 타입: {self.model_type}. (local/claude/gpt/gemini)")

    def generate(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if self.model_type == "claude":
            response = self._client.messages.create(
                model=self._model_name,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text

        elif self.model_type == "gemini":
            prompt = f"{system}\n\n{user}"
            response = self._client.generate_content(prompt)
            return response.text

        elif self.model_type == "gpt":
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content

        else:  # local — Gemma 등 system role 미지원, thinking 모델 대응
            combined_user = f"{system}\n\n---\n\n{user}"
            # thinking 모델은 reasoning 토큰을 먼저 소비하므로 max_tokens를 충분히 설정
            actual_max = max(max_tokens * 3, 6000)
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "user", "content": combined_user},
                ],
                max_tokens=actual_max,
                temperature=0.7,
            )
            msg = response.choices[0].message
            # content가 None이면 reasoning에서 fallback
            if msg.content:
                return msg.content
            reasoning = getattr(msg, 'reasoning', None)
            if reasoning:
                return reasoning
            return ""
