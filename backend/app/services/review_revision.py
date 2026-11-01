"""Apply only a reviewed, unambiguous local replacement to a new version."""
from app.core.exceptions import AppError
from app.db.repositories.writing_repo import WritingRepository
from app.schemas.consistency import ApplyReviewRequest, ConsistencyReviewResponse
from app.schemas.writing import ChapterWorkspaceResponse


def apply_review_revision(
    review: ConsistencyReviewResponse, payload: ApplyReviewRequest, repo: WritingRepository,
) -> ChapterWorkspaceResponse:
    workspace = repo.get_chapter_workspace(review.chapter_id)
    if review.is_stale or workspace.latest_content != payload.expected_content:
        raise AppError("STALE_REVIEW", "正文或前文已变化，请保存当前正文并重新审查。", status_code=409)
    if payload.issue_index >= len(review.issues):
        raise AppError("REVIEW_ISSUE_NOT_FOUND", "审查项不存在。", status_code=404)
    issue = review.issues[payload.issue_index]
    quote = issue.evidence_quote
    if not quote.strip() or not issue.suggested_rewrite.strip() or workspace.latest_content.count(quote) != 1:
        raise AppError("AMBIGUOUS_REVIEW_QUOTE", "原文无法唯一精确定位，请手动修改或重新审查。", status_code=409)
    updated = workspace.latest_content.replace(quote, issue.suggested_rewrite, 1)
    return repo.save_chapter_content(review.chapter_id, updated, source="ai", create_new_version=True)
