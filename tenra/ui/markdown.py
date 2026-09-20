import html as html_mod
import re
from tenra.ui.colors import Colors

def markdown_to_html(text: str) -> str:
    escaped = html_mod.escape(text)

    code_blocks = []
    def save_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        lang_label = f'<span style="color:#7d8590;font-size:10px;float:right;">{html_mod.escape(lang)}</span>' if lang else ""
        ph = f"___CODEBLOCK_{len(code_blocks)}___"
        block = (
            f'<div style="background:{Colors.TERMINAL_BG.name()};border:1px solid {Colors.BORDER.name()};'
            f'border-radius:8px;margin:10px 0;overflow:hidden;">'
            f'<div style="padding:6px 14px 4px;border-bottom:1px solid {Colors.BORDER.name()};'
            f'background:{Colors.BG_CARD.name()};">{lang_label}'
            f'<span style="color:{Colors.ACCENT_PURPLE.name()};font-size:10px;font-family:Consolas;">&#x25CF; kod</span>'
            f'</div>'
            f'<pre style="font-family:Consolas,monospace;font-size:12px;color:#c9d1d9;'
            f'padding:12px 16px;margin:0;white-space:pre-wrap;">{code.strip()}</pre>'
            f'</div>'
        )
        code_blocks.append(block)
        return ph

    processed = re.sub(r"```([a-zA-Z0-9_-]*)\n(.*?)\n```", save_code_block, escaped, flags=re.DOTALL)

    inline_codes = []
    def save_inline(match):
        code = match.group(1)
        ph = f"___INLINE_{len(inline_codes)}___"
        inline_codes.append(
            f'<code style="font-family:Consolas,monospace;background:{Colors.BG_CARD2.name()};'
            f'color:{Colors.ACCENT_PURPLE.name()};padding:2px 6px;border-radius:4px;font-size:12px;">'
            f'{code}</code>'
        )
        return ph

    processed = re.sub(r"`([^`\n]+)`", save_inline, processed)
    processed = re.sub(r"\*\*([^\*]+)\*\*", r"<b>\1</b>", processed)
    processed = re.sub(r"\*([^\*]+)\*", r"<i>\1</i>", processed)

    lines = processed.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)[-\*]\s+(.+)$", line)
        if m:
            lines[i] = f'{m.group(1)}<span style="color:{Colors.ACCENT.name()};">▸</span> {m.group(2)}'
    processed = "\n".join(lines)

    processed = processed.replace("\n", "<br>")

    for idx, block in enumerate(code_blocks):
        processed = processed.replace(f"___CODEBLOCK_{idx}___", block)
    for idx, code in enumerate(inline_codes):
        processed = processed.replace(f"___INLINE_{idx}___", code)

    return processed


def make_tool_card_html(func_name: str, result: str, success: bool = True) -> str:
    """Araç çalıştırma kartı HTML'i üretir."""
    icons = {
        "web_search": "🔍", "browse_website": "🌐", "run_command": "⚡",
        "create_file": "📄", "write_file": "📝", "patch": "🔧",
        "read_file": "📖", "delete_file": "🗑", "move_to_trash": "🗑",
        "execute_python": "🐍", "open_app": "🚀", "open_url": "🔗",
        "search_files": "🔎", "list_directory": "📁", "list_desktop": "🖥",
        "create_folder": "📁", "get_system_info": "💻",
    }
    icon = icons.get(func_name, "⚙️")
    status_color = Colors.ACCENT_GREEN.name() if success else Colors.ACCENT_RED.name()
    status_icon = "✓" if success else "✗"
    border_color = Colors.ACCENT_GREEN.name() if success else Colors.ACCENT_RED.name()

    safe_result = html_mod.escape(str(result))

    return (
        f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.BORDER.name()};'
        f'border-left:3px solid {border_color};border-radius:8px;padding:10px 14px;margin:6px 0;">'
        f'<div style="display:flex;align-items:center;margin-bottom:4px;">'
        f'<span style="font-size:13px;margin-right:8px;">{icon}</span>'
        f'<span style="color:{Colors.ACCENT_PURPLE.name()};font-family:Consolas;font-size:12px;font-weight:bold;">{func_name}</span>'
        f'<span style="margin-left:auto;color:{status_color};font-size:11px;font-weight:bold;">{status_icon}</span>'
        f'</div>'
        f'<div style="color:{Colors.TEXT_MUTED.name()};font-size:12px;font-family:Consolas;">{safe_result[:300]}</div>'
        f'</div>'
    )


def make_terminal_card_html(command: str, stdout: str, stderr: str, exit_code: int) -> str:
    """Terminal komutu çıktısı için özel kart."""
    safe_cmd = html_mod.escape(command)
    safe_out = html_mod.escape(stdout[:2000]) if stdout else ""
    safe_err = html_mod.escape(stderr[:500]) if stderr else ""
    exit_ok = exit_code == 0
    exit_color = Colors.ACCENT_GREEN.name() if exit_ok else Colors.ACCENT_RED.name()
    exit_icon = "✓" if exit_ok else "✗"

    output_html = ""
    if safe_out:
        output_html += f'<pre style="color:#c9d1d9;margin:0;padding:0;white-space:pre-wrap;font-size:11px;">{safe_out}</pre>'
    if safe_err:
        output_html += f'<pre style="color:{Colors.ACCENT_RED.name()};margin:0;padding:0;white-space:pre-wrap;font-size:11px;">{safe_err}</pre>'
    if not safe_out and not safe_err:
        output_html = f'<span style="color:{Colors.TEXT_DIM.name()};font-size:11px;">(çıktı yok)</span>'

    return (
        f'<div style="background:{Colors.TERMINAL_BG.name()};border:1px solid {Colors.BORDER.name()};'
        f'border-radius:8px;margin:8px 0;overflow:hidden;">'
        f'<div style="padding:7px 14px;background:{Colors.BG_CARD.name()};border-bottom:1px solid {Colors.BORDER.name()};'
        f'display:flex;align-items:center;">'
        f'<span style="color:{Colors.TEXT_DIM.name()};font-family:Consolas;font-size:10px;">⚡ Terminal</span>'
        f'<span style="margin-left:10px;color:{Colors.ACCENT.name()};font-family:Consolas;font-size:11px;">$ {safe_cmd}</span>'
        f'<span style="margin-left:auto;color:{exit_color};font-size:11px;font-weight:bold;">exit {exit_code} {exit_icon}</span>'
        f'</div>'
        f'<div style="padding:10px 14px;max-height:200px;overflow-y:auto;">{output_html}</div>'
        f'</div>'
    )


def make_diff_card_html(filename: str, diff_text: str) -> str:
    """Dosya değişikliği için diff kartı."""
    lines = diff_text.split("\n")
    rows = ""
    adds = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))

    for line in lines[:40]:
        safe = html_mod.escape(line)
        if line.startswith("+") and not line.startswith("+++"):
            rows += f'<div style="background:{Colors.DIFF_ADD_BG.name()};color:{Colors.ACCENT_GREEN.name()};font-family:Consolas;font-size:11px;padding:1px 10px;">{safe}</div>'
        elif line.startswith("-") and not line.startswith("---"):
            rows += f'<div style="background:{Colors.DIFF_DEL_BG.name()};color:{Colors.ACCENT_RED.name()};font-family:Consolas;font-size:11px;padding:1px 10px;">{safe}</div>'
        elif line.startswith("@@"):
            rows += f'<div style="color:{Colors.ACCENT_BLUE.name()};font-family:Consolas;font-size:10px;padding:1px 10px;">{safe}</div>'
        else:
            rows += f'<div style="color:{Colors.TEXT_MUTED.name()};font-family:Consolas;font-size:11px;padding:1px 10px;">{safe}</div>'

    safe_fname = html_mod.escape(filename)
    return (
        f'<div style="background:{Colors.BG_CARD.name()};border:1px solid {Colors.BORDER.name()};'
        f'border-radius:8px;margin:8px 0;overflow:hidden;">'
        f'<div style="padding:7px 14px;background:{Colors.BG_CARD2.name()};border-bottom:1px solid {Colors.BORDER.name()};">'
        f'<span style="color:#e6edf3;font-family:Consolas;font-size:11px;">📄 {safe_fname}</span>'
        f'<span style="margin-left:12px;color:{Colors.ACCENT_GREEN.name()};font-size:10px;">+{adds}</span>'
        f'<span style="margin-left:6px;color:{Colors.ACCENT_RED.name()};font-size:10px;">-{dels}</span>'
        f'</div>'
        f'<div>{rows}</div>'
        f'</div>'
    )
