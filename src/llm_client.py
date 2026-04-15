import os
import re
import time


LOCAL_BASE_URL = "http://localhost:8080/v1"
LOCAL_DEFAULT_MODEL = "mlx-community/gemma-4-e4b-it-4bit"


def _empty_usage() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


class LLMClient:
    def __init__(self, model_type: str, local_model: str = LOCAL_DEFAULT_MODEL):
        self.model_type = model_type
        self.local_model = local_model
        self._client = None
        self._model_name = None
        self._usage_records: list[dict] = []
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
            from google import genai
            api_key = os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY 환경변수가 설정되지 않았습니다.")
            self._client = genai.Client(api_key=api_key)
            self._model_name = "gemini-2.0-flash"

        else:
            raise ValueError(f"지원하지 않는 모델 타입: {self.model_type}. (local/claude/gpt/gemini)")

    @property
    def display_name(self) -> str:
        """리포트에 표시할 모델 이름"""
        if self.model_type == "local":
            return self._model_name  # 실제 모델명 반환
        return self._model_name

    def _record_usage(self, response, model_type: str) -> None:
        """모델별 usage 파싱 후 내부 리스트에 기록"""
        try:
            if model_type == "claude":
                u = response.usage
                rec = {
                    "prompt_tokens": u.input_tokens,
                    "completion_tokens": u.output_tokens,
                    "total_tokens": u.input_tokens + u.output_tokens,
                }
            elif model_type == "gemini":
                m = response.usage_metadata
                rec = {
                    "prompt_tokens": getattr(m, "prompt_token_count", 0) or 0,
                    "completion_tokens": getattr(m, "candidates_token_count", 0) or 0,
                    "total_tokens": getattr(m, "total_token_count", 0) or 0,
                }
            else:  # local, gpt (OpenAI 호환)
                u = response.usage
                rec = {
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                    "total_tokens": u.total_tokens,
                }
        except Exception:
            rec = _empty_usage()

        self._usage_records.append(rec)

    def pop_usage(self) -> list[dict]:
        """축적된 usage 기록을 반환하고 초기화 (UsageTracker.add_step에 전달)"""
        records = self._usage_records.copy()
        self._usage_records.clear()
        return records

    def generate(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if self.model_type == "claude":
            response = self._client.messages.create(
                model=self._model_name,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            self._record_usage(response, "claude")
            return response.content[0].text

        elif self.model_type == "gemini":
            from google.genai import types as genai_types
            prompt = f"{system}\n\n{user}"
            for attempt in range(3):
                try:
                    response = self._client.models.generate_content(
                        model=self._model_name,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=system,
                            max_output_tokens=4000,
                            temperature=0.7,
                        ),
                    )
                    self._record_usage(response, "gemini")
                    return response.text
                except Exception as e:
                    msg = str(e)
                    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                        # retryDelay 파싱 (예: retryDelay: '25s')
                        m = re.search(r"retryDelay.*?(\d+)s", msg)
                        wait = int(m.group(1)) + 2 if m else 30
                        print(f"  ⏳ Gemini 할당량 초과 — {wait}초 후 재시도 ({attempt+1}/3)...")
                        time.sleep(wait)
                        if attempt == 2:
                            raise
                    else:
                        raise

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
            self._record_usage(response, "gpt")
            return response.choices[0].message.content

        else:  # local — Gemma 등 system role 미지원, thinking 모델 대응
            combined_user = f"{system}\n\n---\n\n{user}"
            actual_max = max(max_tokens * 3, 6000)
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[{"role": "user", "content": combined_user}],
                max_tokens=actual_max,
                temperature=0.7,
            )
            self._record_usage(response, "local")
            msg = response.choices[0].message
            if msg.content:
                return msg.content
            reasoning = getattr(msg, "reasoning", None)
            if reasoning:
                return reasoning
            return ""
