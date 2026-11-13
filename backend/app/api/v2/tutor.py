"""MENTORX v2/v3 API: the adaptive tutor (Mathematics, Geography map skills). Auth is shared
with /api/v1/auth. Reads "for the student" are scoped to the student's current subject."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser
from app.tutor import admin, ai, assess, llm, practice, recommend, resources, state, views
from app.tutor import profile as profile_service
from app.tutor.models import SkillState
from app.tutor.schemas import (
    AiStatusUpdate,
    AnswerRequest,
    CompletionRequest,
    ExplainRequest,
    GoalRequest,
    ItemActive,
    ModeRequest,
    OnboardingRequest,
    PaceSuggestionAnswer,
    PracticeAnswer,
    PrerequisiteIn,
    ProfileUpdate,
    ResourceIn,
    SkillDescription,
    StartAssessment,
    StartPractice,
    SubjectChoice,
)

router = APIRouter(tags=["tutor"])


# ---------------------------------------------------------------- profile & onboarding


@router.get("/profile")
def get_profile(user: CurrentUser, db: DB) -> dict:
    out = profile_service.out(db, user)
    db.commit()  # goal achievement timestamp (audit 4.8)
    return out


@router.post("/onboarding")
def onboarding(req: OnboardingRequest, user: CurrentUser, db: DB) -> dict:
    p = profile_service.onboard(
        db,
        user,
        req.goal_type,
        req.focus_skill_id,
        req.goal_kind,
        req.goal_target,
        subject_code=req.subject_code,
        grade=req.grade,
        pace_preference=req.pace_preference,
    )
    state.refresh(db, user.id, p.subject_id)
    db.commit()
    return profile_service.out(db, user)


NULLABLE_PROFILE_FIELDS = {"grade", "focus_skill_id", "goal_type"}


@router.patch("/profile")
def update_profile(req: ProfileUpdate, user: CurrentUser, db: DB) -> dict:
    p = profile_service.require(db, user)
    data = {
        k: v
        for k, v in req.model_dump(exclude_unset=True).items()
        if v is not None or k in NULLABLE_PROFILE_FIELDS
    }
    profile_service.check_update(db, p, data)
    for k, v in data.items():
        setattr(p, k, v)
    if "pace_preference" in data:
        state.refresh(db, user.id, p.subject_id)  # modes depend on the pace preference
    if {"pace_preference", "goal_type", "focus_skill_id", "grade"} & data.keys():
        recommend.generate(db, user.id, "profile", subject_id=p.subject_id)
    db.commit()
    return profile_service.out(db, user)


@router.get("/subjects")
def list_subjects(user: CurrentUser, db: DB) -> list[dict]:
    return profile_service.subjects_out(db, user)


@router.put("/profile/subject")
def set_subject(req: SubjectChoice, user: CurrentUser, db: DB) -> dict:
    p = profile_service.set_subject(db, user, req.code)
    state.refresh(db, user.id, p.subject_id)
    recommend.generate(db, user.id, "profile", subject_id=p.subject_id)
    db.commit()
    return profile_service.out(db, user)


@router.get("/home")
def home(user: CurrentUser, db: DB) -> dict:
    return views.home(db, user)


@router.post("/home/pace-suggestion")
def pace_suggestion(req: PaceSuggestionAnswer, user: CurrentUser, db: DB) -> dict:
    views.answer_pace_suggestion(db, user, req.accept)
    return profile_service.out(db, user)


@router.put("/goal")
def set_goal(req: GoalRequest, user: CurrentUser, db: DB) -> dict:
    profile_service.require(db, user)
    profile_service.set_goal(db, user, req.kind, req.target, req.skill_id)
    db.commit()
    return profile_service.goal_progress(db, user) or {}


# ---------------------------------------------------------------- catalog & learning views


@router.get("/subject")
def subject(user: CurrentUser, db: DB) -> dict:
    return views.catalog(db, user)


@router.get("/diagnosis")
def diagnosis(user: CurrentUser, db: DB) -> dict:
    return views.diagnosis(db, user)


@router.get("/dashboard")
def dashboard(user: CurrentUser, db: DB) -> dict:
    return views.dashboard(db, user)


@router.get("/path")
def learning_path(user: CurrentUser, db: DB) -> dict:
    return views.learning_path(db, user)


@router.get("/analytics")
def analytics(user: CurrentUser, db: DB) -> dict:
    return views.analytics(db, user)


@router.get("/skills/{skill_id}")
def skill(skill_id: int, user: CurrentUser, db: DB) -> dict:
    return views.skill_detail(db, user, skill_id)


@router.patch("/skills/{skill_id}/mode")
def set_mode(skill_id: int, req: ModeRequest, user: CurrentUser, db: DB) -> dict:
    profile_service.require(db, user)
    st = db.get(SkillState, (user.id, skill_id))
    if st is None:
        from app.core.errors import AppError

        raise AppError(404, "skill_not_found", "That skill isn't available.")
    st.mode_override = req.mode
    db.commit()
    return views.skill_detail(db, user, skill_id)


# ---------------------------------------------------------------- assessments


@router.post("/assessments", status_code=status.HTTP_201_CREATED)
def start_assessment(req: StartAssessment, user: CurrentUser, db: DB) -> dict:
    return assess.to_out(db, assess.start(db, user, req.kind, req.skill_id))


@router.get("/assessments")
def list_assessments(user: CurrentUser, db: DB) -> list[dict]:
    return assess.list_for(db, user)


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    return assess.get(db, user, assessment_id)


@router.get("/assessments/{assessment_id}/next")
def assessment_next(assessment_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    return assess.next_item(db, user, assessment_id)


@router.post("/assessments/{assessment_id}/answer")
def assessment_answer(
    assessment_id: uuid.UUID, req: AnswerRequest, user: CurrentUser, db: DB
) -> dict:
    return assess.answer(db, user, assessment_id, req.item_id, req.response())


# ---------------------------------------------------------------- practice


@router.post("/practice", status_code=status.HTTP_201_CREATED)
def start_practice(req: StartPractice, user: CurrentUser, db: DB) -> dict:
    s = practice.start(db, user, req.skill_id, req.guided, req.kind)
    return {
        "id": s.id,
        "kind": s.kind,
        "skill_id": s.skill_id,
        "mode": s.mode,
        "guided": s.guided,
        "difficulty": s.difficulty,
        "total": s.target_count,
        "answered": s.answered_count,
    }


@router.get("/practice/{session_id}/next")
def practice_next(session_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    return practice.next_item(db, user, session_id)


@router.post("/practice/{session_id}/hint")
def practice_hint(
    session_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    ai_hint: bool = Query(default=False, alias="ai"),
) -> dict:
    return practice.hint(db, user, session_id, use_ai=ai_hint)


@router.post("/practice/{session_id}/answer")
def practice_answer(session_id: uuid.UUID, req: PracticeAnswer, user: CurrentUser, db: DB) -> dict:
    return practice.answer(db, user, session_id, req.item_id, req.response(), req.reveal)


@router.post("/practice/{session_id}/end")
def practice_end(session_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    return practice.end(db, user, session_id)


# ---------------------------------------------------------------- AI tutor


@router.get("/ai/status")
def ai_status(user: CurrentUser, db: DB) -> dict:
    return ai.status(db, user)


@router.post("/ai/explain")
def ai_explain(req: ExplainRequest, user: CurrentUser, db: DB) -> dict:
    return ai.explain(db, user, req.interaction_id)


# ---------------------------------------------------------------- resources


@router.get("/resources")
def resource_library(
    user: CurrentUser,
    db: DB,
    kind: str | None = Query(default=None, max_length=20),
    q: str | None = Query(default=None, max_length=60),
) -> list[dict]:
    return resources.library(db, user, kind, q)


@router.post("/resources/{resource_id}/complete")
def complete_resource(resource_id: int, req: CompletionRequest, user: CurrentUser, db: DB) -> dict:
    return resources.set_completed(db, user, resource_id, req.completed)


# ---------------------------------------------------------------- admin


SubjectParam = Query(default="MATH", alias="subject", max_length=20)


@router.get("/admin/overview")
def admin_overview(user: CurrentUser, db: DB, subject: str = SubjectParam) -> dict:
    admin.require_admin(user)
    return admin.overview(db, subject)


@router.get("/admin/model")
def admin_model(user: CurrentUser, db: DB, subject: str = SubjectParam) -> dict:
    admin.require_admin(user)
    return admin.model_monitor(db, subject)


@router.get("/admin/ai")
def admin_ai(user: CurrentUser, db: DB) -> list[dict]:
    admin.require_admin(user)
    return ai.admin_list(db)


@router.post("/admin/ai/test")
def admin_ai_test(user: CurrentUser) -> dict:
    admin.require_admin(user)
    return llm.check_connection()


@router.patch("/admin/ai/{row_id}")
def admin_ai_status(row_id: int, req: AiStatusUpdate, user: CurrentUser, db: DB) -> dict:
    admin.require_admin(user)
    return ai.admin_set_status(db, row_id, req.status)


@router.get("/admin/skills")
def admin_skills(
    user: CurrentUser,
    db: DB,
    q: str | None = Query(default=None, max_length=60),
    subject: str = SubjectParam,
) -> list[dict]:
    admin.require_admin(user)
    return admin.skills(db, q, subject)


@router.patch("/admin/skills/{skill_id}")
def admin_update_skill(skill_id: int, req: SkillDescription, user: CurrentUser, db: DB) -> dict:
    admin.require_admin(user)
    return admin.update_skill(db, skill_id, req.description)


@router.get("/admin/skills/{skill_id}/items")
def admin_items(skill_id: int, user: CurrentUser, db: DB) -> list[dict]:
    admin.require_admin(user)
    return admin.items(db, skill_id)


@router.patch("/admin/items/{item_id}")
def admin_item(item_id: int, req: ItemActive, user: CurrentUser, db: DB) -> dict:
    admin.require_admin(user)
    return admin.set_item_active(db, item_id, req.is_active)


@router.get("/admin/resources")
def admin_resources(user: CurrentUser, db: DB, skill_id: int | None = None) -> list[dict]:
    admin.require_admin(user)
    return admin.list_resources(db, skill_id)


@router.post("/admin/resources", status_code=status.HTTP_201_CREATED)
def admin_create_resource(req: ResourceIn, user: CurrentUser, db: DB) -> dict:
    admin.require_admin(user)
    return admin.save_resource(db, req.model_dump())


@router.patch("/admin/resources/{resource_id}")
def admin_update_resource(resource_id: int, req: ResourceIn, user: CurrentUser, db: DB) -> dict:
    admin.require_admin(user)
    return admin.save_resource(db, req.model_dump(), resource_id)


@router.delete("/admin/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_resource(resource_id: int, user: CurrentUser, db: DB) -> None:
    admin.require_admin(user)
    admin.delete_resource(db, resource_id)


@router.get("/admin/prerequisites")
def admin_prerequisites(user: CurrentUser, db: DB) -> list[dict]:
    admin.require_admin(user)
    return admin.prerequisites(db)


@router.post("/admin/prerequisites", status_code=status.HTTP_201_CREATED)
def admin_add_prerequisite(req: PrerequisiteIn, user: CurrentUser, db: DB) -> dict:
    admin.require_admin(user)
    return admin.add_prerequisite(db, req.skill_id, req.prerequisite_id, user)


@router.delete(
    "/admin/prerequisites/{skill_id}/{prerequisite_id}", status_code=status.HTTP_204_NO_CONTENT
)
def admin_remove_prerequisite(
    skill_id: int, prerequisite_id: int, user: CurrentUser, db: DB
) -> None:
    admin.require_admin(user)
    admin.remove_prerequisite(db, skill_id, prerequisite_id)
