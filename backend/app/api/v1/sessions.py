from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser
from app.schemas.sessions import (
    AnswerRequest,
    AnswerResult,
    QuestionOut,
    SessionOut,
    StartSessionRequest,
)
from app.services import quiz

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start(req: StartSessionRequest, user: CurrentUser, db: DB) -> SessionOut:
    """Start a session, or resume the active one of the same kind."""
    return quiz.to_out(db, quiz.start_session(db, user, req))


@router.get("", response_model=list[SessionOut])
def history(user: CurrentUser, db: DB) -> list[SessionOut]:
    return quiz.list_sessions(db, user)


@router.get("/{session_id}", response_model=SessionOut)
def read(session_id: uuid.UUID, user: CurrentUser, db: DB) -> SessionOut:
    return quiz.session_detail(db, user, session_id)


@router.post("/{session_id}/next", response_model=QuestionOut)
def next_question(session_id: uuid.UUID, user: CurrentUser, db: DB) -> QuestionOut:
    return quiz.next_question(db, user, session_id)


@router.post("/{session_id}/answer", response_model=AnswerResult)
def answer(session_id: uuid.UUID, req: AnswerRequest, user: CurrentUser, db: DB) -> AnswerResult:
    return quiz.answer(db, user, session_id, req.question_id, req.selected_key)


@router.post("/{session_id}/end", response_model=SessionOut)
def end(session_id: uuid.UUID, user: CurrentUser, db: DB) -> SessionOut:
    return quiz.to_out(db, quiz.end_session(db, user, session_id))
