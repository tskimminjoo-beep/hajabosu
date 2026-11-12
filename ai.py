"""AI 호출은 이 파일에서만 한다. 키와 모델은 .env에서 읽는다.

.env
  ANTHROPIC_API_KEY=...   (필수)
  MODEL=...               (필수, 예: claude-haiku-5-5)
"""
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", encoding="utf-8")

접수정리_지침 = ROOT / "지침" / "접수정리.md"

# 지침/접수정리.md의 JSON 키와 같아야 한다. 값이 없으면 null.
접수정리_스키마 = {
    "type": "object",
    "properties": {
        "원문파일": {"type": "string"},
        "접수일": {"type": ["string", "null"]},
        "위치": {"type": ["string", "null"]},
        "공종": {"type": ["string", "null"]},
        "하자내용": {"type": "string"},
        "긴급도": {"type": "string", "enum": ["긴급", "높음", "보통"]},
        "판단근거": {"type": "string"},
        "확인필요사유": {"type": ["string", "null"]},
    },
    "required": [
        "원문파일", "접수일", "위치", "공종", "하자내용",
        "긴급도", "판단근거", "확인필요사유",
    ],
    "additionalProperties": False,
}


def _client() -> anthropic.Anthropic:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(".env에 ANTHROPIC_API_KEY가 없습니다.")
    return anthropic.Anthropic()  # 키는 환경변수에서 읽는다


def _model() -> str:
    model = os.getenv("MODEL")
    if not model:
        raise RuntimeError(".env에 MODEL이 없습니다.")
    return model


def 접수정리(원문파일: str | Path) -> dict:
    """접수 원문 txt 1건을 읽어 지침/접수정리.md대로 정리한 dict를 돌려준다."""
    원문파일 = Path(원문파일)
    원문 = 원문파일.read_text(encoding="utf-8")
    지침 = 접수정리_지침.read_text(encoding="utf-8")

    response = _client().messages.create(
        model=_model(),
        max_tokens=4000,
        system=지침,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": 접수정리_스키마},
        },
        messages=[{
            "role": "user",
            "content": f"원문파일: {원문파일.name}\n\n--- 접수 원문 ---\n{원문}",
        }],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError(f"AI가 응답을 거부했습니다: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("응답이 max_tokens에서 잘렸습니다.")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)
