"""Bağlam (context) kullanım tahmini — Cursor tarzı % göstergesi."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from tenra.config import DEFAULT_NUM_CTX, MAX_HISTORY


def estimate_tokens(text: str) -> int:
    """Basit token tahmini (Türkçe/kod için ~4 karakter ≈ 1 token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _history_chars(messages: List[Dict[str, Any]], max_msgs: int = MAX_HISTORY) -> int:
    total = 0
    for msg in (messages or [])[-max_msgs:]:
        content = msg.get("content", "")
        if isinstance(content, str):
            # agent.optimize ile aynı üst sınır fikri
            if len(content) > 1500:
                total += 500 + 300 + 40  # kısaltılmış yaklaşık
            else:
                total += len(content)
        total += 8  # role overhead
    return total


def estimate_context_usage(
    chat_history: List[Dict[str, Any]],
    workspace_path: Optional[str] = None,
    workspace_name: Optional[str] = None,
    query: Optional[str] = None,
    num_ctx: int = DEFAULT_NUM_CTX,
    prompt_eval_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Sistem + geçmiş (+ opsiyonel Ollama prompt_eval) → kullanım özeti.

    Dönüş:
      used_tokens, limit, percent, label, tooltip
    """
    system_chars = 0
    try:
        from tenra.config import get_system_prompt
        system = get_system_prompt(workspace_path, workspace_name, query=query)
        system_chars = len(system or "")
    except Exception:
        system_chars = 1200  # kabaca

    hist_chars = _history_chars(chat_history)
    # Araç şemaları her turda gönderilir — sabit ek yük
    tools_overhead = 1800

    estimated = estimate_tokens(
        "x" * (system_chars + hist_chars)
    ) + estimate_tokens("x" * tools_overhead)

    if prompt_eval_count and prompt_eval_count > 0:
        used = int(prompt_eval_count)
        source = "ollama"
    else:
        used = estimated
        source = "estimate"

    limit = max(1, int(num_ctx or DEFAULT_NUM_CTX))
    percent = min(100, max(0, round(100 * used / limit)))

    def _fmt(n: int) -> str:
        if n >= 1000:
            return f"{n / 1000:.1f}k".replace(".0k", "k")
        return str(n)

    label = f"{percent}% bağlam"
    detail = f"{_fmt(used)} / {_fmt(limit)}"
    tooltip = (
        f"Bu sohbetin bağlam penceresi\n"
        f"Kullanılan: {_fmt(used)} token\n"
        f"Limit: {_fmt(limit)} (num_ctx)\n"
        f"Kaynak: {'Ollama ölçümü' if source == 'ollama' else 'tahmini'}\n"
        f"Sistem≈{_fmt(estimate_tokens('x'*system_chars))} · "
        f"Geçmiş≈{_fmt(estimate_tokens('x'*hist_chars))} · "
        f"Araçlar≈{_fmt(estimate_tokens('x'*tools_overhead))}"
    )

    return {
        "used_tokens": used,
        "limit": limit,
        "percent": percent,
        "label": label,
        "detail": detail,
        "tooltip": tooltip,
        "source": source,
    }


def context_badge_color(percent: int) -> str:
    """Rozet rengi — düşük yeşilimsi, yüksek uyarı."""
    if percent >= 85:
        return "#dc645f"
    if percent >= 65:
        return "#c8a050"
    return "#8c8c91"
