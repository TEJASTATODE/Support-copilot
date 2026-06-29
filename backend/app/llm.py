"""LLM generation via an OpenAI-compatible endpoint.

Why OpenAI-compatible and not a vendor-specific SDK:
The same client code works with OpenAI, Anthropic (via proxy), Groq, Together,
and local Ollama -- just three env vars change. That provider-agnostic design
is a deliberate architecture decision worth saying out loud in interviews.
"""
from openai import AsyncOpenAI
from app.config import settings

_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


async def complete(system: str, user: str, temperature: float = 0.2) -> str:
    resp = await _client.chat.completions.create(
        model=settings.llm_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()