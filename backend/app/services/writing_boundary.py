"""Check a writing plan against actual preceding prose before streaming a draft."""
from pydantic import BaseModel, Field

from app.core.exceptions import AppError
from app.db.repositories.settings_repo import SettingsRepository
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json


class EvidencedEvent(BaseModel):
    statement: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)


class WritingBoundary(BaseModel):
    # 不限制条数：长章节的已确立事实/重复事件可能很多，截断会让合法响应被判非法。
    # 这些只是生成前的参考信息，列表长短不影响后续正文生成。
    established: list[EvidencedEvent] = Field(default_factory=list)
    repeated_events: list[EvidencedEvent] = Field(default_factory=list)
    next_step: str = Field(min_length=1)


async def check_writing_boundary(
    *, novel_uid: str, chapter_id: int, settings: SettingsRepository,
    history: str, plan: str,
) -> str:
    if not history.strip():
        return ""
    _, base_url, model, api_key = settings.get_credentials_for_task("planning")
    result = await complete_chat(
        base_url=base_url, api_key=api_key, model=model, temperature=0.2,
        system_prompt=(
            "你是小说章节衔接编辑。仅依据已写正文检查本次写作计划，不生成正文。"
            "提取与本次计划有关的已发生事件、人物实际所知、关系、时间地点和物品最终状态；"
            "不要把叙述者知识分给所有角色。发现计划重演前文时，指出已发生的部分，"
            "建议从事件后果继续推进；如果本章目标已写完，建议简短收束，不凑字数、不另造事件。"
            "前文若为草稿，只作衔接参考，不宣称已经定稿。"
        ),
        user_prompt=(
            f"【已写正文】\n{history}\n\n【本次写作计划】\n{plan}\n\n"
            '返回严格 JSON：{"established":[{"statement":"已确立状态",'
            '"evidence_quote":"已写正文的连续原句"}],'
            '"repeated_events":[{"statement":"计划中已经发生、应跳过的事件",'
            '"evidence_quote":"已写正文的连续原句"}],'
            '"next_step":"本次新增推进及结束边界，不改变既定剧情方向"}。'
            "没有证据的项目不要输出，列表可以为空。证据不得拼接、改写或使用省略号。"
        ),
        novel_uid=novel_uid, chapter_id=chapter_id, task_type="writing_boundary",
        timeout_sec=90.0,
    )
    boundary = await parse_and_validate_json(result.content, WritingBoundary)
    for event in boundary.established + boundary.repeated_events:
        if event.evidence_quote not in history:
            raise AppError(
                "BOUNDARY_EVIDENCE_MISMATCH", "章节衔接检查的证据与前文不匹配，请重试；原正文未改动。",
                status_code=502,
            )
    return (
        "【生成前章节衔接检查】以下是基于原文证据的写作边界；与梗概重复时从已发生事件之后推进。\n"
        + boundary.model_dump_json()
    )
