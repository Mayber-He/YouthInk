"""Author requirements take precedence over optional style presets."""
from app.schemas.novel import NovelDetail


def author_style_prompt(novel: NovelDetail) -> str:
    return (
        f"作品叙事要求：基调：{novel.tone or '未指定'}；叙事视角：{novel.pov or '未指定'}。\n"
        f"作者详细写作要求：{novel.style_note or '未指定'}\n"
        "作者明确要求优先于通用模板和示例；全知叙述者可以提供角色不知道的信息，"
        "但角色的言行仍只能基于其实际所知。不要将叙述者知识误判为角色知识。"
    )
