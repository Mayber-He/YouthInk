"""Six-layer Prompt assembler and variable renderer (Design Doc Section 7.1 & Dev Doc 4.5)."""

from __future__ import annotations

import re
from typing import Any

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_template(template_text: str, variables: dict[str, Any]) -> str:
    """Replace {{var_name}} placeholders in template_text with values from variables."""

    def _replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        val = variables.get(key, "")
        return str(val) if val is not None else ""

    return _VAR_PATTERN.sub(_replacer, template_text)


def assemble_six_layer_prompt(
    *,
    layer1_system_role: str,
    layer2_style_template: str = "",
    layer3_core_setting: str = "",
    layer4_dynamic_context: str = "",
    layer5_task_instruction: str = "",
    layer6_output_format: str = "",
) -> tuple[str, str]:
    """
    Assemble the prompt strictly following the prefix-cache friendly order:
    ① 系统角色 -> ② 风格模板 -> ③ 作品核心设定 -> ④ 动态上下文 -> ⑤ 任务指令 -> ⑥ 输出格式要求.

    Returns (system_message, user_message).
    """
    system_parts = [f"【① 系统角色】\n{layer1_system_role.strip()}"]
    if layer2_style_template.strip():
        system_parts.append(f"【② 风格规范】\n{layer2_style_template.strip()}")
    if layer3_core_setting.strip():
        system_parts.append(f"【③ 作品核心设定】\n{layer3_core_setting.strip()}")

    user_parts: list[str] = []
    if layer4_dynamic_context.strip():
        user_parts.append(f"【④ 上下文与约束】\n{layer4_dynamic_context.strip()}")
    if layer5_task_instruction.strip():
        user_parts.append(f"【⑤ 当前任务指令】\n{layer5_task_instruction.strip()}")
    if layer6_output_format.strip():
        user_parts.append(f"【⑥ 输出格式要求】\n{layer6_output_format.strip()}")

    return "\n\n".join(system_parts), "\n\n".join(user_parts)
