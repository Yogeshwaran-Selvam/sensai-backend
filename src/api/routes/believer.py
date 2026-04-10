import json
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel, Field

from api.llm import run_llm_with_openai
from api.db.course import get_course as get_course_from_db, get_keywords_for_milestone
from api.db.task import get_task
from api.db.utils import construct_description_from_blocks
from api.models import (
    BelieverStartRequest,
    BelieverStartResponse,
    BelieverTopicInfo,
    BelieverNextRequest,
    BelieverNextResponse,
    BelieverReportRequest,
    BelieverReportResponse,
    TaskType,
)
from api.prompts import compile_prompt
from api.prompts.believer_mode import (
    BELIEVER_SYSTEM_PROMPT,
    BELIEVER_USER_PROMPT,
    BELIEVER_REPORT_SYSTEM_PROMPT,
    BELIEVER_REPORT_USER_PROMPT,
)
from api.config import openai_plan_to_model_name
from api.utils.logging import logger

router = APIRouter()


# ============================================================
# Pydantic models for LLM structured output
# ============================================================

class LLMBelieverQuestion(BaseModel):
    question_text: str = Field(description="The question text")
    options: List[str] = Field(description="Exactly 4 answer options")
    correct_answer: str = Field(
        description="The correct answer text, must exactly match one of the options"
    )
    explanation: str = Field(description="Why the correct answer is correct")
    topic: str = Field(description="The topic/keyword this question tests")
    difficulty: str = Field(description="easy, medium, or hard")


class LLMBelieverOutput(BaseModel):
    question: LLMBelieverQuestion = Field(description="The generated question")


class LLMReportOutput(BaseModel):
    overall_assessment: str = Field(description="2-3 sentence overall assessment")
    study_recommendations: List[str] = Field(
        description="List of specific, actionable study recommendations"
    )


# ============================================================
# Helper: Get learning content from a milestone
# ============================================================

async def get_milestone_learning_content(course_id: int, milestone_id: int) -> str:
    """Get all learning material text from a milestone."""
    course = await get_course_from_db(course_id, only_published=False)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    target_milestone = None
    for milestone in course.get("milestones", []):
        if milestone["id"] == milestone_id:
            target_milestone = milestone
            break

    if not target_milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    content_parts = []
    for task_info in target_milestone.get("tasks", []):
        if task_info["type"] == TaskType.LEARNING_MATERIAL:
            task_data = await get_task(task_info["id"])
            if task_data and task_data.get("blocks"):
                text = construct_description_from_blocks(task_data["blocks"])
                if text.strip():
                    content_parts.append(
                        f"## {task_data.get('title', 'Untitled')}\n\n{text}"
                    )

    if not content_parts:
        raise HTTPException(
            status_code=400,
            detail="No learning material found. Add learning materials first.",
        )

    return "\n\n---\n\n".join(content_parts)


# ============================================================
# Helper: Generate a single question for a topic
# ============================================================

async def generate_question_for_topic(
    content: str, topic: str, difficulty: str
) -> dict:
    """Generate a single MCQ question for a specific topic and difficulty."""
    messages = compile_prompt(
        BELIEVER_SYSTEM_PROMPT,
        BELIEVER_USER_PROMPT,
        learning_material_content=content,
        topic=topic,
        difficulty=difficulty,
    )

    try:
        result = await run_llm_with_openai(
            model=openai_plan_to_model_name["text-mini"],
            messages=messages,
            response_model=LLMBelieverOutput,
            max_output_tokens=2048,
        )
        q = result.question
        return {
            "question_text": q.question_text,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "topic": topic,
            "difficulty": difficulty,
        }
    except Exception as e:
        logger.error(f"Error generating believer question: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate question: {str(e)}"
        )


# ============================================================
# Route: Start a Believer Mode session
# ============================================================

@router.post("/start", response_model=BelieverStartResponse)
async def start_believer_session(request: BelieverStartRequest):
    """
    Starts an adaptive diagnostic session:
    - Fetches keywords/topics from the milestone
    - Generates the first HARD question for the first topic
    - Returns the session config
    """
    # 1. Get keywords for this milestone
    keywords = await get_keywords_for_milestone(request.milestone_id)

    if not keywords or len(keywords) == 0:
        raise HTTPException(
            status_code=400,
            detail="No topics/keywords found for this module. Keywords are needed to run Believer Mode.",
        )

    # Limit to 8 topics max for a reasonable session length
    topics = keywords[:8]

    # 2. Get learning content
    content = await get_milestone_learning_content(
        request.course_id, request.milestone_id
    )

    # 3. Build topic info
    topic_infos = [
        BelieverTopicInfo(keyword=kw, status="pending", current_difficulty="hard")
        for kw in topics
    ]

    # 4. Generate first question (HARD for first topic)
    first_question = await generate_question_for_topic(
        content, topics[0], "hard"
    )

    logger.info(
        f"Believer Mode started: {len(topics)} topics from milestone {request.milestone_id}"
    )

    return BelieverStartResponse(
        topics=topic_infos,
        first_question=first_question,
        current_topic_index=0,
        learning_content=content,
    )


# ============================================================
# Route: Submit answer and get next question/action
# ============================================================

DIFFICULTY_SEQUENCE = ["hard", "medium", "easy"]

@router.post("/next", response_model=BelieverNextResponse)
async def get_next_believer_question(request: BelieverNextRequest):
    """
    Receives the learner's answer, determines what happens next:
    - If correct → topic mastered at this difficulty, move to next topic
    - If wrong at hard → try medium for same topic
    - If wrong at medium → try easy for same topic
    - If wrong at easy → topic is weak, move to next topic
    """
    current_diff_index = DIFFICULTY_SEQUENCE.index(request.current_difficulty)
    topic = request.current_topic

    if request.was_correct:
        # Determine mastery level based on difficulty
        mastery_map = {"hard": "strong", "medium": "moderate", "easy": "basic"}
        mastery = mastery_map.get(request.current_difficulty, "basic")

        topic_result = {
            "keyword": topic,
            "status": mastery,
            "passed_at": request.current_difficulty,
        }

        feedback = f"✅ Correct! You've demonstrated {mastery} understanding of '{topic}'."

        # Check if we hit the limit or have no more topics
        is_done = len(request.remaining_topics) == 0 or request.questions_asked >= 10

        # Move to next topic validation
        if is_done:
            return BelieverNextResponse(
                is_session_complete=True,
                feedback=feedback,
                topic_result=topic_result,
            )

        # Generate question for next topic
        next_topic = request.remaining_topics[0]
        content = await get_milestone_learning_content(
            request.course_id, request.milestone_id
        )
        next_question = await generate_question_for_topic(
            content, next_topic, "hard"
        )

        return BelieverNextResponse(
            is_session_complete=False,
            next_question=next_question,
            next_topic=next_topic,
            next_difficulty="hard",
            topic_result=topic_result,
            feedback=feedback,
        )

    else:
        # Wrong answer
        if current_diff_index < len(DIFFICULTY_SEQUENCE) - 1:
            # Try easier difficulty for SAME topic
            next_difficulty = DIFFICULTY_SEQUENCE[current_diff_index + 1]

            feedback = f"❌ Not quite. Let's try an easier question about '{topic}'."

            # If we hit the absolute limit of 10 questions total
            if request.questions_asked >= 10:
                return BelieverNextResponse(
                    is_session_complete=True,
                    feedback=f"❌ Incorrect. We've hit the maximum of 10 questions for this session. Excellent practice!",
                    # Send partial result so far
                    topic_result={
                        "keyword": topic,
                        "status": "weak",
                        "passed_at": "none",
                    }
                )

            content = await get_milestone_learning_content(
                request.course_id, request.milestone_id
            )
            next_question = await generate_question_for_topic(
                content, topic, next_difficulty
            )

            return BelieverNextResponse(
                is_session_complete=False,
                next_question=next_question,
                next_topic=topic,
                next_difficulty=next_difficulty,
                feedback=feedback,
            )

        else:
            # Failed all difficulties for this topic → WEAK
            topic_result = {
                "keyword": topic,
                "status": "weak",
                "passed_at": "none",
            }

            feedback = f"❌ '{topic}' seems to be an area for improvement. Let's move on."

            # Check if we hit the limit or have no more topics
            is_done = len(request.remaining_topics) == 0 or request.questions_asked >= 10

            # Move to next topic validation
            if is_done:
                return BelieverNextResponse(
                    is_session_complete=True,
                    feedback=feedback,
                    topic_result=topic_result,
                )

            next_topic = request.remaining_topics[0]
            content = await get_milestone_learning_content(
                request.course_id, request.milestone_id
            )
            next_question = await generate_question_for_topic(
                content, next_topic, "hard"
            )

            return BelieverNextResponse(
                is_session_complete=False,
                next_question=next_question,
                next_topic=next_topic,
                next_difficulty="hard",
                topic_result=topic_result,
                feedback=feedback,
            )


# ============================================================
# Route: Generate diagnostic report
# ============================================================

@router.post("/report", response_model=BelieverReportResponse)
async def generate_believer_report(request: BelieverReportRequest):
    """
    Generates an AI-powered diagnostic report from the session results.
    """
    overall_score = (
        (request.correct_count / request.total_count * 100)
        if request.total_count > 0
        else 0
    )

    # Format topic results for the prompt
    topic_results_text = ""
    topic_mastery = []
    for tr in request.topic_results:
        status = tr.get("status", "unknown")
        passed_at = tr.get("passed_at", "none")
        keyword = tr.get("keyword", "Unknown")

        score_map = {"strong": 100, "moderate": 66, "basic": 33, "weak": 0}
        score = score_map.get(status, 0)

        topic_results_text += f"- {keyword}: {status.upper()} (passed at: {passed_at})\n"
        topic_mastery.append({
            "keyword": keyword,
            "status": status,
            "score": score,
        })

    messages = compile_prompt(
        BELIEVER_REPORT_SYSTEM_PROMPT,
        BELIEVER_REPORT_USER_PROMPT,
        module_name=request.module_name,
        topic_results=topic_results_text,
        overall_score=f"{overall_score:.0f}",
        correct_count=str(request.correct_count),
        total_count=str(request.total_count),
    )

    try:
        result = await run_llm_with_openai(
            model=openai_plan_to_model_name["text-mini"],
            messages=messages,
            response_model=LLMReportOutput,
            max_output_tokens=2048,
        )

        return BelieverReportResponse(
            overall_assessment=result.overall_assessment,
            study_recommendations=result.study_recommendations,
            topic_mastery=topic_mastery,
            overall_score=overall_score,
        )
    except Exception as e:
        logger.error(f"Error generating believer report: {e}")
        # Return a basic report if AI fails
        return BelieverReportResponse(
            overall_assessment=f"You scored {overall_score:.0f}% overall on this module.",
            study_recommendations=[
                f"Review topics marked as 'weak': {', '.join(t['keyword'] for t in topic_mastery if t['status'] == 'weak')}"
            ],
            topic_mastery=topic_mastery,
            overall_score=overall_score,
        )
