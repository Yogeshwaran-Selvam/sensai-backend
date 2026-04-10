"""Recruiter MCQ generation routes.

Three flows are exposed under /recruiter/mcq/*:
  - from-suggested : generate questions from a JD already suggested by SensAI
  - from-own-jd    : recruiter uploads (PDF/DOCX/text) or pastes their own JD
  - from-jd-resume : recruiter provides both a JD and a candidate resume

Generation is performed asynchronously; the client polls GET /recruiter/mcq/{gen_id}
to observe progress. When a JD is classified as unstructured, a synthesized
pseudo-JD is returned with status="awaiting_confirmation" so the recruiter can
review / edit before questions are actually generated. A confirmation endpoint
then kicks off the actual generation.
"""

import json
import traceback
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile, File

from api.db.recruiter import (
    create_recruiter_generation,
    get_recruiter_generation,
    list_recruiter_generations,
    update_recruiter_generation,
)
from api.db.recruiter_test import (
    create_attempt,
    create_recruiter_test,
    get_attempt,
    get_attempt_counts_for_org,
    get_test_by_code,
    get_test_by_id,
    list_attempts_for_test,
    list_tests_for_org,
    submit_attempt,
    update_attempt_answers,
)
from api.utils.logging import logger
from api.models import (
    ConfirmSynthesizedJDRequest,
    GenerateFromSuggestedRequest,
    PublishTestRequest,
    RecruiterDifficulty,
    RecruiterFlow,
    RecruiterQuestionType,
    ReviewMultipleAnswersRequest,
    StartAttemptRequest,
    SubmitAttemptRequest,
    SynthesizedJD,
    UpdateQuestionsRequest,
)
from api.services.recruiter_mcq import (
    run_from_suggested_flow,
    run_generation_after_confirmation,
    run_jd_resume_classification,
    run_own_jd_classification,
    synthesized_jd_to_text,
)
from api.utils.doc_extract import extract_text, extract_text_from_upload

router = APIRouter()


# ---------------------------------------------------------------------------
# Flow A — from a suggested JD
# ---------------------------------------------------------------------------

@router.post("/mcq/from-suggested")
async def from_suggested(
    request: GenerateFromSuggestedRequest,
    background: BackgroundTasks,
):
    try:
        record = await create_recruiter_generation(
            org_id=request.org_id,
            flow=RecruiterFlow.from_suggested.value,
            status="pending",
        )
        background.add_task(
            run_from_suggested_flow,
            record["id"],
            request.jd_title,
            request.jd_description,
            request.jd_responsibilities,
            request.jd_skills,
            request.num_questions,
            request.difficulty,
            request.type_mix,
        )
        return {"id": record["id"], "status": "pending"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"from_suggested failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Flow B — recruiter provides their own JD (file or text)
# ---------------------------------------------------------------------------

@router.post("/mcq/from-own-jd")
async def from_own_jd(
    background: BackgroundTasks,
    org_id: int = Form(...),
    jd_text: str = Form(default=""),
    jd_file: UploadFile = File(default=None),
):
    try:
        has_file = jd_file is not None and getattr(jd_file, "filename", "")
        if not jd_text and not has_file:
            raise HTTPException(
                status_code=400,
                detail="Provide either jd_text or jd_file",
            )

        jd_plain = ""
        if has_file:
            jd_plain = await extract_text_from_upload(jd_file)
        if jd_text:
            jd_plain = (jd_plain + "\n\n" + jd_text).strip() if jd_plain else jd_text.strip()

        if not jd_plain:
            raise HTTPException(status_code=400, detail="JD content is empty")

        record = await create_recruiter_generation(
            org_id=org_id,
            flow=RecruiterFlow.own_jd.value,
            status="parsing",
            jd_text=jd_plain,
        )

        background.add_task(run_own_jd_classification, record["id"], jd_plain)
        return {"id": record["id"], "status": "parsing"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"from_own_jd failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Flow C — recruiter provides JD + resume
# ---------------------------------------------------------------------------

@router.post("/mcq/from-jd-resume")
async def from_jd_resume(
    background: BackgroundTasks,
    org_id: int = Form(...),
    jd_text: str = Form(default=""),
    resume_text: str = Form(default=""),
    jd_file: UploadFile = File(default=None),
    resume_file: UploadFile = File(default=None),
):
    try:
        has_jd_file = jd_file is not None and getattr(jd_file, "filename", "")
        has_resume_file = resume_file is not None and getattr(resume_file, "filename", "")

        if not jd_text and not has_jd_file:
            raise HTTPException(
                status_code=400, detail="Provide either jd_text or jd_file"
            )
        if not resume_text and not has_resume_file:
            raise HTTPException(
                status_code=400, detail="Provide either resume_text or resume_file"
            )

        jd_plain = ""
        if has_jd_file:
            jd_plain = await extract_text_from_upload(jd_file)
        if jd_text:
            jd_plain = (jd_plain + "\n\n" + jd_text).strip() if jd_plain else jd_text.strip()

        resume_plain = ""
        if has_resume_file:
            resume_plain = await extract_text_from_upload(resume_file)
        if resume_text:
            resume_plain = (
                (resume_plain + "\n\n" + resume_text).strip()
                if resume_plain
                else resume_text.strip()
            )

        if not jd_plain or not resume_plain:
            raise HTTPException(status_code=400, detail="JD or resume content is empty")

        record = await create_recruiter_generation(
            org_id=org_id,
            flow=RecruiterFlow.jd_resume.value,
            status="parsing",
            jd_text=jd_plain,
            resume_text=resume_plain,
        )

        background.add_task(
            run_jd_resume_classification, record["id"], jd_plain, resume_plain
        )
        return {"id": record["id"], "status": "parsing"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"from_jd_resume failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Confirmation — used for flows B/C after the recruiter reviews the (possibly
# synthesized) JD. Also usable for flow A if the recruiter wants to tweak the
# grounding JD before generation.
# ---------------------------------------------------------------------------

@router.post("/mcq/{gen_id}/confirm")
async def confirm_and_generate(
    gen_id: int,
    request: ConfirmSynthesizedJDRequest,
    background: BackgroundTasks,
):
    record = await get_recruiter_generation(gen_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found")

    if record["status"] not in ("awaiting_confirmation", "done", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm while status is '{record['status']}'",
        )

    # Persist (possibly edited) synthesized JD back into the record, then run.
    from api.db.recruiter import update_recruiter_generation

    if request.jd is not None:
        # Unstructured path — user reviewed/edited the synthesized JD
        override_grounding = synthesized_jd_to_text(request.jd)
        updated = await update_recruiter_generation(
            gen_id,
            status="generating",
            synthesized_jd=request.jd.model_dump(),
        )
    else:
        # Structured path — use the original JD text as grounding
        override_grounding = record.get("jd_text") or ""
        updated = await update_recruiter_generation(gen_id, status="generating")

    background.add_task(
        run_generation_after_confirmation,
        gen_id,
        updated,
        request.num_questions,
        request.difficulty,
        request.type_mix,
        None,
        override_grounding,
    )
    return {"id": gen_id, "status": "generating"}


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

@router.get("/mcq/{gen_id}")
async def get_generation(gen_id: int):
    record = await get_recruiter_generation(gen_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found")
    return record


@router.get("/mcq")
async def list_generations(org_id: int, limit: int = 50):
    return await list_recruiter_generations(org_id, limit=limit)


# ---------------------------------------------------------------------------
# Edit / delete questions on a generation (before publishing)
# ---------------------------------------------------------------------------

@router.patch("/mcq/{gen_id}/questions")
async def update_generation_questions(gen_id: int, request: UpdateQuestionsRequest):
    record = await get_recruiter_generation(gen_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found")
    updated = await update_recruiter_generation(
        gen_id,
        questions=[q.model_dump() for q in request.questions],
    )
    return updated


# ---------------------------------------------------------------------------
# Publish a generation as a test with a unique access code
# ---------------------------------------------------------------------------

def _strip_answers_for_candidate(questions: list) -> list:
    """Remove answer keys before sending questions to a candidate."""
    out = []
    for q in questions:
        qc = dict(q)
        qc.pop("correct_index", None)
        qc.pop("expected_solution", None)
        qc.pop("expected_answer", None)
        qc.pop("rationale", None)
        out.append(qc)
    return out


@router.post("/mcq/{gen_id}/publish")
async def publish_generation(gen_id: int, request: PublishTestRequest):
    record = await get_recruiter_generation(gen_id)
    if not record:
        raise HTTPException(status_code=404, detail="Generation not found")

    questions = (
        [q.model_dump() for q in request.questions]
        if request.questions is not None
        else (record.get("questions") or [])
    )
    if not questions:
        raise HTTPException(status_code=400, detail="No questions to publish")

    test = await create_recruiter_test(
        org_id=record["org_id"],
        title=request.title,
        questions=questions,
        generation_id=gen_id,
    )
    return {
        "id": test["id"],
        "test_code": test["test_code"],
        "title": test["title"],
        "question_count": len(questions),
    }


# ---------------------------------------------------------------------------
# Recruiter-side test listing and attempt inspection
# ---------------------------------------------------------------------------

@router.get("/tests")
async def list_recruiter_tests(org_id: int):
    tests = await list_tests_for_org(org_id)
    attempt_counts = await get_attempt_counts_for_org(org_id)
    result = []
    for t in tests:
        tid = t["id"]
        counts = attempt_counts.get(tid, {})
        result.append({
            "id": tid,
            "test_code": t["test_code"],
            "title": t["title"],
            "question_count": len(t["questions"]),
            "created_at": t["created_at"],
            "attempt_total": counts.get("total", 0),
            "attempt_submitted": counts.get("submitted", 0),
            "attempt_in_progress": counts.get("in_progress", 0),
            "avg_score": counts.get("avg_score"),
            "max_score": counts.get("max_score"),
        })
    return result


@router.get("/tests/{test_id}")
async def get_recruiter_test_detail(test_id: int):
    test = await get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return {
        "id": test["id"],
        "test_code": test["test_code"],
        "title": test["title"],
        "questions": test["questions"],
        "question_count": len(test["questions"]),
        "status": test["status"],
        "created_at": test["created_at"],
    }


@router.get("/tests/{test_id}/attempts")
async def list_attempts(test_id: int):
    test = await get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return await list_attempts_for_test(test_id)


@router.get("/tests/{test_id}/attempts/{attempt_id}")
async def get_attempt_detail(test_id: int, attempt_id: int):
    test = await get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    attempt = await get_attempt(attempt_id)
    if not attempt or attempt["test_id"] != test_id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    return {
        "attempt": attempt,
        "test": {
            "id": test["id"],
            "title": test["title"],
            "test_code": test["test_code"],
            "questions": test["questions"],
        },
    }


@router.patch("/tests/{test_id}/attempts/{attempt_id}/review")
async def review_attempt_answers(
    test_id: int, attempt_id: int, request: ReviewMultipleAnswersRequest
):
    """Approve or reject individual code/text answers on a submitted attempt."""
    test = await get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    attempt = await get_attempt(attempt_id)
    if not attempt or attempt["test_id"] != test_id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.get("status") != "submitted":
        raise HTTPException(status_code=400, detail="Can only review submitted attempts")

    questions = test["questions"]
    answers = list(attempt.get("answers") or [])
    answers_by_idx = {a["question_index"]: a for a in answers}

    for review in request.reviews:
        idx = review.question_index
        if idx < 0 or idx >= len(questions):
            raise HTTPException(
                status_code=400, detail=f"Invalid question_index: {idx}"
            )
        q = questions[idx]
        if q.get("type") == "mcq":
            raise HTTPException(
                status_code=400,
                detail=f"Question {idx} is MCQ and auto-scored; cannot manually review",
            )
        if idx not in answers_by_idx:
            raise HTTPException(
                status_code=400, detail=f"No answer found for question {idx}"
            )
        ans = answers_by_idx[idx]
        ans["review_verdict"] = review.verdict.value
        ans["review_feedback"] = review.feedback
        ans["reviewed_at"] = datetime.now(timezone.utc).isoformat()

    updated_answers = [answers_by_idx.get(a["question_index"], a) for a in answers]
    updated = await update_attempt_answers(attempt_id, updated_answers)
    return {
        "attempt": updated,
        "test": {
            "id": test["id"],
            "title": test["title"],
            "test_code": test["test_code"],
            "questions": test["questions"],
        },
    }


# ---------------------------------------------------------------------------
# Candidate-facing endpoints (identified by test_code)
# ---------------------------------------------------------------------------

@router.get("/tests/code/{test_code}")
async def get_test_public(test_code: str):
    test = await get_test_by_code(test_code)
    if not test or test.get("status") != "active":
        raise HTTPException(status_code=404, detail="Invalid or inactive test code")
    return {
        "id": test["id"],
        "test_code": test["test_code"],
        "title": test["title"],
        "question_count": len(test["questions"]),
    }


@router.post("/tests/code/{test_code}/start")
async def start_test_attempt(test_code: str, request: StartAttemptRequest):
    test = await get_test_by_code(test_code)
    if not test or test.get("status") != "active":
        raise HTTPException(status_code=404, detail="Invalid or inactive test code")

    if not request.candidate_name.strip() or not request.candidate_email.strip():
        raise HTTPException(status_code=400, detail="Name and email are required")

    attempt = await create_attempt(
        test_id=test["id"],
        candidate_name=request.candidate_name.strip(),
        candidate_email=request.candidate_email.strip(),
    )
    return {
        "attempt_id": attempt["id"],
        "test": {
            "id": test["id"],
            "title": test["title"],
            "test_code": test["test_code"],
            "questions": _strip_answers_for_candidate(test["questions"]),
        },
    }


def _score_answers(questions: list, answers: list) -> tuple:
    """Auto-score MCQs. Code/text are left for manual review."""
    mcq_correct = 0
    mcq_total = 0
    for ans in answers:
        idx = ans.get("question_index")
        if idx is None or idx < 0 or idx >= len(questions):
            continue
        q = questions[idx]
        if q.get("type") == "mcq":
            mcq_total += 1
            if (
                ans.get("mcq_selected_index") is not None
                and ans["mcq_selected_index"] == q.get("correct_index")
            ):
                mcq_correct += 1
    # Denominator uses total MCQ questions in the set (not just attempted),
    # so partial attempts don't look artificially perfect.
    total_mcq_in_set = sum(1 for q in questions if q.get("type") == "mcq")
    max_score = float(total_mcq_in_set) if total_mcq_in_set else 0.0
    score = float(mcq_correct)
    return score, max_score


@router.post("/tests/attempts/{attempt_id}/submit")
async def submit_test_attempt(attempt_id: int, request: SubmitAttemptRequest):
    attempt = await get_attempt(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.get("status") == "submitted":
        raise HTTPException(status_code=400, detail="Attempt already submitted")

    test = await get_test_by_id(attempt["test_id"])
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    answers = [a.model_dump() for a in request.answers]
    score, max_score = _score_answers(test["questions"], answers)
    updated = await submit_attempt(attempt_id, answers, score, max_score)
    return {
        "attempt_id": updated["id"],
        "score": updated["score"],
        "max_score": updated["max_score"],
        "submitted_at": updated["submitted_at"],
        "note": "MCQ auto-scored. Code and text answers are saved for manual review.",
    }
