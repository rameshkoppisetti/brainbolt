import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.http.deps import get_db, get_redis_client
from app.http.schemas import (
    MetricsResponse,
    NextQuestionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.realtime.socketio import sio
from app.services.errors import (
    NoEligibleQuestionsError,
    NoQuestionsError,
    NotCurrentQuestion,
    QuestionAlreadyMastered,
    QuestionNotFound,
    StateVersionConflict,
    UserNotFound,
)
from app.services.metrics_service import get_metrics as get_metrics_service
from app.services.quiz_service import next_question as next_question_service
from app.services.quiz_service import submit_answer as submit_answer_service


router = APIRouter()


@router.get("/next", response_model=NextQuestionResponse)
def next_question(
    userId: str = Query(...),
    sessionId: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
) -> NextQuestionResponse:
    try:
        return next_question_service(user_id=userId, session_id=sessionId, db=db, r=r)
    except NoEligibleQuestionsError:
        raise HTTPException(status_code=404, detail="no_eligible_questions")
    except NoQuestionsError:
        raise HTTPException(status_code=500, detail="no_questions_seeded")


@router.post("/answer", response_model=SubmitAnswerResponse)
async def submit_answer(
    body: SubmitAnswerRequest,
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
) -> SubmitAnswerResponse:
    try:
        result = submit_answer_service(body=body, db=db, r=r)
    except QuestionNotFound:
        raise HTTPException(status_code=404, detail="question_not_found")
    except StateVersionConflict:
        raise HTTPException(status_code=409, detail="state_version_conflict")
    except NotCurrentQuestion:
        raise HTTPException(status_code=409, detail="not_current_question")
    except QuestionAlreadyMastered:
        raise HTTPException(status_code=409, detail="question_already_mastered")

    if result.emitted_payload is not None:
        await sio.emit("leaderboard:update", result.emitted_payload)
    return result.response


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    userId: str = Query(...),
    db: Session = Depends(get_db),
    r: redis.Redis = Depends(get_redis_client),
) -> MetricsResponse:
    try:
        return get_metrics_service(user_id=userId, db=db, r=r)
    except UserNotFound:
        raise HTTPException(status_code=404, detail="user_not_found")

