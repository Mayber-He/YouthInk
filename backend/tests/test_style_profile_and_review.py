"""Unit & integration tests for Phase 3 (Style Profile learning) and Phase 4 (Dynamic Pacing & Surgical Style Review)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_global_db, get_novel_db
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.novel_repo import create_novel_project
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.schemas.entities import CharacterCreate, LocationCreate
from app.schemas.novel import NovelCreate
from app.schemas.outline import ArcCreate, ChapterCreate, VolumeCreate
from app.schemas.settings import StyleTemplateCreate, StyleTemplateUpdate
from app.schemas.style_profile import StyleProfile
from app.schemas.writing import SceneCreate, StreamWriteRequest
from app.services.prompt.prose_prompt import style_layer
from app.services.prompt.style_profile import (
    analyze_reference_excerpt,
    compute_language_metrics,
    render_style_profile_prompt_block,
    sanitize_profile_against_source,
    select_dynamic_scene_pacing,
)
from app.services.repetition_service import clean_dangling_seam_particles
from app.services.style_review import (
    apply_surgical_span_rewrites,
    diagnose_chapter_style,
    validate_span_replacement_safety,
)
from app.services.writing_service import WritingService

SAMPLE_REFERENCE_EXCERPT = """
“你这箱子里装的石头啊？”林渡拎起她的行李箱，手腕往下沉了半寸，顺手把箱子换到自己右手边。
“全是专业书，要你管。”许知意把遮阳帽往下压了压，没伸手去接，“你要是拎不动就放着，我自己拖上去。”
“得了吧，四楼没电梯，等你拖上去食堂早收摊了。”
他迈上两级台阶，步子迈得不算快，刚好停在她抬脚能跟上的位置。
“身份证拿稳，待会儿宿管阿姨查得严。”
“知道了，啰嗦。”
她嘴上嫌弃，还是低头把帆布包侧袋的拉链拉开一半，确认那张卡片还在指尖能碰到的地方。
""".strip()


def test_analyze_reference_excerpt_extracts_six_dimensions_and_never_copies_source() -> None:
    profile, derived, notes = analyze_reference_excerpt(SAMPLE_REFERENCE_EXCERPT, genre="校园")
    assert isinstance(profile, StyleProfile)
    assert profile.source_type == "reference_excerpt"
    assert profile.language.metrics.char_count > 100
    assert profile.language.metrics.dialogue_ratio_pct > 30.0
    assert profile.language.colloquial_level
    assert profile.narrative.pov_mode
    assert profile.dialogue.subtext_technique
    assert profile.emotion.whitespace_and_restraint
    assert profile.pacing.closing_hook
    assert profile.genre_traits.genre_name == "青春校园"
    assert derived["pov"] in ("第三人称限知", "第一人称")
    assert notes

    # Anti-copy guarantee: no 7+ char substring from the reference text may appear in the profile
    compact_src = "".join(SAMPLE_REFERENCE_EXCERPT.split())
    profile_dump = render_style_profile_prompt_block(profile)
    for i in range(len(compact_src) - 7 + 1):
        gram = compact_src[i : i + 7]
        assert gram not in profile_dump, f"verbatim source substring leaked into StyleProfile: {gram}"


def test_sanitize_profile_against_source_strips_accidental_verbatim_phrases() -> None:
    profile = StyleProfile()
    profile.dialogue.subtext_technique = "模仿“你这箱子里装的石头啊”这种反问方式呈现潜台词"
    cleaned = sanitize_profile_against_source(profile, SAMPLE_REFERENCE_EXCERPT)
    assert "你这箱子里装的石头啊" not in cleaned.dialogue.subtext_technique


def test_dynamic_scene_pacing_selects_mode_by_beat_type() -> None:
    m1, d1 = select_dynamic_scene_pacing("目标：两人在微信上聊报到时间并互相调侃\n必须发生：互发消息")
    assert m1 == "dialogue_spar"
    assert "高频互动拉扯" in d1

    m2, d2 = select_dynamic_scene_pacing("目标：江澈认出学姐就是网友，决定暂不点破\n终点状态：压在心里")
    assert m2 == "key_choice_turning"
    assert "暗涌破绽与抉择" in d2

    m3, d3 = select_dynamic_scene_pacing("目标：夜里独处时想起白天的尴尬沉默")
    assert m3 == "emotional_undertow"
    assert "情绪暗涌与留白" in d3

    m4, d4 = select_dynamic_scene_pacing("目标：去食堂买午饭并偶遇室友", scene_index=1, total_scenes=3)
    assert m4 == "incident_progression"
    assert "现场事件推进" in d4


def test_style_review_detects_real_project_ai_pathologies_and_rewrites_spans_only() -> None:
    flawed_prose = (
        "了，江澈把身份证递进窗口。\n\n"
        "他低头看着手机，拇指悬在屏幕上方半秒，终究没有按下去，把手机翻过来屏幕朝下扣在桌面上。\n\n"
        "听到这句话，林夏不由得怔住了，陆川嘴角勾起一抹弧度，她心里泛起一丝异样的情愫。\n\n"
        "“你也是今天报到？”\n\n"
        "“嗯。”\n\n"
        "“东西都领齐了吗？”\n\n"
        "“行。”"
    )
    report = diagnose_chapter_style(flawed_prose, chapter_id=1, beat="微信聊天与报到交接")
    assert report.total_issues >= 4
    issue_types = {i.issue_type for i in report.issues}
    assert "broken_rewrite_seam" in issue_types
    assert "stock_micro_action" in issue_types
    assert "direct_emotion_telling" in issue_types or "over_ornamented_simile" in issue_types
    assert "monosyllabic_dialogue_wall" in issue_types

    rewrite_res = apply_surgical_span_rewrites(flawed_prose, report.issues, max_spans=6)
    assert rewrite_res.replaced_count >= 3
    out = rewrite_res.rewritten_text
    # Broken seam particle at the head of paragraph 1 is gone
    assert not out.startswith("了，")
    assert "江澈把身份证递进窗口。" in out
    # Stock micro-action is surgically replaced without dropping surrounding plot
    assert "拇指悬在屏幕上方" not in out
    assert "屏幕朝下扣在桌面上" not in out
    assert "不由得怔住了" not in out
    assert "嘴角勾起一抹弧度" not in out
    # Untouched dialogue lines remain intact
    assert "“你也是今天报到？”" in out
    assert "“东西都领齐了吗？”" in out


def test_span_replacement_safety_blocks_date_loss_and_meta_markers() -> None:
    ok1, reason1 = validate_span_replacement_safety("九月一日早上8点他到了校门", "早上他到了校门")
    assert not ok1 and "8" in reason1

    ok2, reason2 = validate_span_replacement_safety("他不由得愣住了。", "【修改后】他愣住了。")
    assert not ok2 and "标记" in reason2


def test_style_profile_db_persistence_and_prompt_injection(tmp_path: Path) -> None:
    reset_config_for_testing(tmp_path / "test_style_profile_db")
    ensure_global_db_initialized()

    profile, derived, _ = analyze_reference_excerpt(SAMPLE_REFERENCE_EXCERPT, genre="校园")

    with get_global_db() as gconn:
        srepo = SettingsRepository(gconn)
        builtin_styles = srepo.list_style_templates()
        assert len(builtin_styles) >= 4
        assert builtin_styles[0].style_profile is not None

        custom = srepo.create_style_template(
            StyleTemplateCreate(
                name="我的校园参考文风",
                pov=str(derived["pov"]),
                tone=str(derived["tone"]),
                sentence_pref=str(derived["sentence_pref"]),
                dialogue_ratio=str(derived["dialogue_ratio"]),
                desc_focus=str(derived["desc_focus"]),
                pacing=str(derived["pacing"]),
                style_profile=profile,
            )
        )
        assert custom.style_profile is not None
        assert custom.style_profile.source_type == "reference_excerpt"

        # Editable: user updates dialogue subtext rule
        edited_profile = custom.style_profile.model_copy(deep=True)
        edited_profile.dialogue.subtext_technique = "多用反问与顺手递东西代替直白关心"
        updated = srepo.update_style_template(
            custom.id, StyleTemplateUpdate(style_profile=edited_profile)
        )
        assert updated.style_profile is not None
        assert "多用反问与顺手递东西" in updated.style_profile.dialogue.subtext_technique

    novel = create_novel_project(
        NovelCreate(
            title="文风注入测试书",
            genre="校园",
            tone="清新",
            pov="第三人称限知",
            protagonist_concept="江澈，大一新生。",
            synopsis="大一开学前夕的网聊与报到偶遇。",
            style_template_id=custom.id,
            style_note="保持轻快生活感。",
        )
    )
    uid = novel.novel_uid
    with get_novel_db(uid) as nconn, get_global_db() as gconn:
        erepo = EntityRepository(nconn)
        orepo = OutlineRepository(nconn)
        wrepo = WritingRepository(nconn)
        srepo = SettingsRepository(gconn)

        erepo.create_character(CharacterCreate(name="江澈", role="male_lead"))
        erepo.create_location(LocationCreate(name="报到处"))
        vol = orepo.create_volume(VolumeCreate(title="卷一"))
        arc = orepo.create_arc(ArcCreate(volume_id=vol.id, title="弧一"))
        ch = orepo.create_chapter(ChapterCreate(arc_id=arc.id, title="第一章", synopsis="微信聊报到"))
        sc = wrepo.create_scene(
            ch.id,
            SceneCreate(beat="目标：两人在微信上聊报到时间\n必须发生：互发消息调侃", target_words=800),
        )

        svc = WritingService(uid, nconn, srepo)
        sys_p, user_p = svc.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch.id, scene_id=sc.id, mode="scene")
        )
        # Layer 2 injects the custom Style Profile even when style_note is present
        assert "【结构化文风档案（Style Profile）】" in sys_p
        assert "多用反问与顺手递东西代替直白关心" in sys_p
        # Layer 5 injects dynamic scene pacing for微信/聊天 scenes
        assert "【本场动态节奏：高频互动拉扯】" in user_p

        # Post-generation style review & span rewrite through WritingService
        wrepo.save_chapter_content(
            ch.id,
            content="了，江澈把身份证递进窗口。\n\n他拇指悬在屏幕上方半秒，不由得怔住了。",
            source="ai",
            create_new_version=True,
        )
        rev = svc.review_chapter_style(ch.id, scene_id=sc.id)
        assert rev.total_issues >= 2
        rew = svc.rewrite_chapter_style_spans(ch.id, save_to_chapter=True)
        assert rew.replaced_count >= 2
        assert not rew.rewritten_text.startswith("了，")
        assert "拇指悬在屏幕上方" not in rew.rewritten_text


def test_existing_prompt_contracts_preserved_with_style_optimization(tmp_path: Path) -> None:
    """Verify all existing T4/T15/T21/M3 prompt contracts remain 100% intact."""
    reset_config_for_testing(tmp_path / "test_contracts")
    ensure_global_db_initialized()

    late_plot = "两人最终结婚并共同创办公司"
    synopsis = "大一开学前的暑假，江澈认识了一个特别的网友。" + late_plot + "。" + "后续剧情很长很长。" * 40

    novel = create_novel_project(
        NovelCreate(
            title="回归契约书",
            genre="校园",
            tone="清新治愈",
            pov="第三人称限知",
            protagonist_concept="江澈，大一新生。",
            synopsis=synopsis,
            style_template_id=1,
            style_note="作者要求：轻松欢脱。",
        )
    )
    uid = novel.novel_uid
    with get_novel_db(uid) as nconn, get_global_db() as gconn:
        erepo = EntityRepository(nconn)
        orepo = OutlineRepository(nconn)
        wrepo = WritingRepository(nconn)
        srepo = SettingsRepository(gconn)

        erepo.create_character(CharacterCreate(name="江澈", role="male_lead"))
        erepo.create_location(LocationCreate(name="报到处"))
        vol = orepo.create_volume(VolumeCreate(title="卷一"))
        arc = orepo.create_arc(ArcCreate(volume_id=vol.id, title="弧一"))
        ch = orepo.create_chapter(ChapterCreate(arc_id=arc.id, title="报到日", synopsis="江澈报到。"))
        s1 = wrepo.create_scene(ch.id, SceneCreate(beat="目标：第1场景\n必须发生：事件1", target_words=800))
        s2 = wrepo.create_scene(
            ch.id,
            SceneCreate(
                beat="目标：让江澈确认学姐就是网友，并决定暂时不揭穿\n起点状态：桌前\n必须发生：填表\n终点状态：压在心里",
                target_words=800,
            ),
        )

        svc = WritingService(uid, nconn, srepo)
        sys_new, user_new = svc.prepare_stream_write_prompts(
            StreamWriteRequest(
                chapter_id=ch.id,
                scene_id=s2.id,
                mode="scene",
                existing_content="本章已写的一段正文。",
            )
        )
        sys_old, _user_old = svc.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch.id, scene_id=s1.id, mode="scene"),
            legacy=True,
        )

        assert late_plot not in (sys_new + user_new)
        assert "核心设定" in sys_new
        assert "禁用套话表达" in sys_new
        assert sys_new.count("示例：") == 2
        assert "作者要求：轻松欢脱。" in sys_new
        assert len(sys_new) < len(sys_old)

        # User prompt block ordering contract
        i_constraint = user_new.index("硬约束清单")
        i_chars = user_new.index("出场人物卡与当前时序状态")
        i_written = user_new.index("本章已写前文")
        i_scene = user_new.index("本章细纲与场景节拍")
        i_task = user_new.index("【⑤ 当前任务指令】")
        assert i_constraint < i_written < i_scene < i_task
        assert i_chars < i_written < i_scene < i_task
        assert "### " not in user_new[i_scene:]
        assert "本场必须以一句明确的内心判断收束，不要只写动作" in user_new
        assert "最后一句用对话、动作或决定结束" in user_new

