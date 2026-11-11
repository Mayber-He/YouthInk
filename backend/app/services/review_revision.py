"""Apply reviewed, unambiguous local replacements to one new version."""
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
    indices = payload.issue_indices if payload.issue_indices is not None else [payload.issue_index]
    replacements = []
    for index in indices:
        if index >= len(review.issues):
            raise AppError("REVIEW_ISSUE_NOT_FOUND", "审查项不存在。", status_code=404)
        issue = review.issues[index]
        quote = issue.evidence_quote
        start = workspace.latest_content.find(quote)
        if (not quote.strip() or not issue.suggested_rewrite.strip() or start < 0
                or workspace.latest_content.find(quote, start + 1) >= 0):
            raise AppError("AMBIGUOUS_REVIEW_QUOTE", "原文无法唯一精确定位，请手动修改或重新审查。", status_code=409)
        replacements.append((start, start + len(quote), issue.suggested_rewrite))
    replacements.sort()
    for previous, current in zip(replacements, replacements[1:]):
        if current[0] < previous[1]:
            raise AppError("OVERLAPPING_REVIEW_QUOTES", "所选建议的原文片段重叠，请分开采用或手动修改。", status_code=409)
    updated = workspace.latest_content
    for start, end, rewrite in reversed(replacements):
        updated = updated[:start] + rewrite + updated[end:]
    return repo.save_chapter_content(review.chapter_id, updated, source="ai", create_new_version=True)
