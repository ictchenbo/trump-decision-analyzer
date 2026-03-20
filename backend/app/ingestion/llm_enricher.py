"""
LLM 增强模块 — 对特朗普言论进行中文翻译和鹰派倾向评分。

配置项（.env）：
  LLM_BASE_URL   — OpenAI 兼容接口地址，如 https://api.openai.com/v1
  LLM_API_KEY    — API 密钥
  LLM_MODEL      — 模型名称，默认 gpt-4o-mini
  LLM_ENABLED    — 是否启用，默认 true；设为 false 时跳过 LLM 调用

提示词配置：
  backend/app/ingestion/prompts/statement_enrich.json
"""

import os
import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# 提示词配置文件路径
_PROMPT_FILE = Path(__file__).parent / "prompts" / "statement_enrich.json"


def _load_prompt_config() -> dict:
    """加载提示词配置，每次调用重新读取以支持热更新。"""
    with open(_PROMPT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_enabled() -> bool:
    return os.environ.get("LLM_ENABLED", "true").lower() not in ("false", "0", "no")


def _get_client_config() -> dict:
    return {
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    }


def enrich_statement(content: str) -> dict:
    """
    对单条言论调用 LLM，返回：
      {
        "translation": str,      # 中文译文
        "hawkish_score": int,    # 鹰派倾向 0-100
        "llm_enriched": bool     # 是否成功调用 LLM
      }
    失败时返回 fallback 值（translation=None, hawkish_score=None, llm_enriched=False）。
    """
    if not _is_enabled():
        return {"translation": None, "hawkish_score": None, "llm_enriched": False}

    cfg = _get_client_config()
    if not cfg["api_key"]:
        logger.warning("LLM_API_KEY 未配置，跳过 LLM 增强")
        return {"translation": None, "hawkish_score": None, "llm_enriched": False}

    try:
        prompt_cfg = _load_prompt_config()
    except Exception as e:
        logger.error(f"加载提示词配置失败: {e}")
        return {"translation": None, "hawkish_score": None, "llm_enriched": False}

    system_msg = prompt_cfg.get("system", "")
    user_template = prompt_cfg.get("user_template", "{content}")
    timeout = prompt_cfg.get("timeout_seconds", 30)
    max_retries = prompt_cfg.get("max_retries", 2)

    user_msg = user_template.replace("{content}", content)

    last_error: Optional[Exception] = None
    resp = None

    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                f"{cfg['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={
                    "model": cfg["model"],
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.1")),
                    "max_tokens": 512,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            raw_json = json.loads(resp.content.decode('utf-8'))
            raw = raw_json["choices"][0]["message"]["content"].strip()

            # 兼容模型在 JSON 外包裹 markdown 代码块的情况
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            # 截断修复：如果 JSON 不完整，尝试补全右括号
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                # 尝试截取到最后一个完整字段
                fixed = raw
                if not fixed.endswith("}"):
                    # 找到最后一个完整的 key:value 对后补 }
                    last_comma = fixed.rfind(",")
                    last_colon = fixed.rfind(":")
                    if last_comma > 0 and last_comma > last_colon:
                        fixed = fixed[:last_comma] + "}"
                    else:
                        fixed = fixed.rstrip() + "}"
                result = json.loads(fixed)
            translation = str(result.get("translation") or "").strip() or None
            score_raw = result.get("hawkish_score")
            hawkish_score = int(score_raw) if score_raw is not None else None
            if hawkish_score is not None:
                hawkish_score = max(0, min(100, hawkish_score))

            # 结构化分级评分（新增字段，向后兼容）
            level_raw = result.get("hawkish_level")
            hawkish_level = int(level_raw) if level_raw is not None else None

            return {
                "translation": translation,
                "hawkish_score": hawkish_score,
                "hawkish_level": hawkish_level,
                "llm_enriched": True,
            }

        except Exception as e:
            if resp:
                print(resp.text)
            last_error = e
            if attempt < max_retries:
                # 429 限流时等待更长时间
                wait = 10 if "429" in str(e) else 1
                time.sleep(wait)

    logger.warning(f"LLM 增强失败（已重试 {max_retries} 次）: {last_error}")
    return {"translation": None, "hawkish_score": None, "llm_enriched": False}


def enrich_statements_batch(statements: list) -> list:
    """
    批量增强言论列表（原地修改每条 dict，并返回列表）。
    已有 translation 和 hawkish_score 的条目跳过，避免重复调用。
    """
    for stmt in statements:
        if stmt.get("translation") is not None and stmt.get("hawkish_score") is not None:
            continue
        content = stmt.get("content", "")
        if not content:
            continue
        enriched = enrich_statement(content)
        stmt.update(enriched)
    return statements
