from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.consistency import ApplyReviewRequest, ConsistencyReviewResponse
from app.services.review_revision import apply_review_revision


class Repo:
    def __init__(self, content):
        self.latest_content = content
        self.saves = []

    def get_chapter_workspace(self, chapter_id):
        return SimpleNamespace(latest_content=self.latest_content)

    def save_chapter_content(self, chapter_id, content, **kwargs):
        self.saves.append((chapter_id, content, kwargs))
        return SimpleNamespace(latest_content=content)


def review(*pairs, stale=False):
    return ConsistencyReviewResponse(
        id=1, chapter_id=2, version_id=3, summary="", issue_count=len(pairs),
        violation_count=0, created_at="", is_stale=stale,
        issues=[dict(check_type="prose", verdict="suspicious", evidence_quote=q,
                     suggested_rewrite=r) for q, r in pairs],
    )


def test_batch_saves_one_version_using_original_positions():
    repo = Repo("甲句。乙句。丙句。")
    report = review(("甲句", "乙句加长"), ("乙句", "改好"), ("丙句", "不选"))
    result = apply_review_revision(report, ApplyReviewRequest(
        issue_indices=[1, 0], expected_content=repo.latest_content), repo)
    assert result.latest_content == "乙句加长。改好。丙句。"
    assert repo.saves == [(2, result.latest_content, {"source": "ai", "create_new_version": True})]


@pytest.mark.parametrize("pairs,content,indices", [
    ([("甲乙", "一"), ("乙丙", "二")], "甲乙丙", [0, 1]),
    ([("甲", "一"), ("乙", "二")], "甲乙乙", [0, 1]),
    ([("甲", "一"), ("丙", "二")], "甲乙", [0, 1]),
    ([("甲", "一"), ("乙", " ")], "甲乙", [0, 1]),
    ([("甲", "一")], "甲乙", [0, 2]),
])
def test_invalid_batch_never_saves(pairs, content, indices):
    repo = Repo(content)
    with pytest.raises(AppError):
        apply_review_revision(review(*pairs), ApplyReviewRequest(
            issue_indices=indices, expected_content=content), repo)
    assert repo.saves == []


@pytest.mark.parametrize("stale,expected", [(True, "甲乙"), (False, "已编辑")])
def test_stale_batch_never_saves(stale, expected):
    repo = Repo("甲乙")
    with pytest.raises(AppError):
        apply_review_revision(review(("甲", "一"), stale=stale), ApplyReviewRequest(
            issue_indices=[0], expected_content=expected), repo)
    assert repo.saves == []


def test_legacy_single_issue_still_works():
    repo = Repo("甲乙")
    assert apply_review_revision(review(("甲", "一")), ApplyReviewRequest(
        issue_index=0, expected_content="甲乙"), repo).latest_content == "一乙"


@pytest.mark.parametrize("fields", [
    {}, {"issue_indices": []}, {"issue_indices": [-1]},
    {"issue_index": 0, "issue_indices": [1]}, {"issue_indices": [0, 0]},
])
def test_invalid_selection_is_rejected(fields):
    with pytest.raises(ValidationError):
        ApplyReviewRequest(expected_content="甲乙", **fields)
