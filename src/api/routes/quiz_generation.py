import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.models import (
    CreateQuizGenerationRequest,
    QuizGenerationResponse,
    TopicWeight,
    GenerateQuestionsRequest,
    RegenerateQuestionRequest,
    QuizGenBloomsDistribution,
)
from api.db.quiz_generation import create_quiz_generation_config, get_quiz_generation_config
from api.llm import run_llm_with_openai
from api.prompts import compile_prompt
from api.prompts.quiz_generation import (
    QUIZ_TOPIC_GENERATION_SYSTEM_PROMPT,
    QUIZ_TOPIC_GENERATION_USER_PROMPT,
    QUIZ_TOPIC_VERIFY_SYSTEM_PROMPT,
    QUIZ_TOPIC_VERIFY_USER_PROMPT,
)
from api.config import openai_plan_to_model_name
from api.utils.logging import logger

router = APIRouter()


# ─── LLM output models ───────────────────────────────────────────────────────

class TopicLLMQuestion(BaseModel):
    question_text: str = Field(description="The full question text")
    topic: str = Field(description="Which topic this question belongs to (must match one of the provided topics exactly)")
    blooms_level: str = Field(description="Bloom's level: remember/understand/apply/analyze/evaluate/create")
    options: Optional[List[str]] = Field(default=None, description="4 options for MCQ, null for other types")
    correct_answer: str = Field(description="The correct answer")
    explanation: str = Field(description="Brief explanation of the correct answer")
    difficulty: str = Field(description="easy, medium, or hard")
    question_type: str = Field(description="objective or subjective")


class TopicLLMOutput(BaseModel):
    questions: List[TopicLLMQuestion] = Field(description="Generated questions list")


class TopicVerificationResult(BaseModel):
    question_index: int = Field(description="0-based index")
    status: str = Field(description="verified, pending, or wrong")
    reason: str = Field(description="Explanation for the status")


class TopicVerificationOutput(BaseModel):
    results: List[TopicVerificationResult]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_topics_list(topic_weights: list) -> str:
    return "\n".join(
        f"- {tw.keyword}: {tw.weight}%" for tw in topic_weights
    )


def _build_blooms_distribution(dist: Optional[QuizGenBloomsDistribution]) -> str:
    if dist is None:
        return "No specific distribution required — use your judgment."
    return (
        f"- Remember: {dist.remember}%\n"
        f"- Understand: {dist.understand}%\n"
        f"- Apply: {dist.apply}%\n"
        f"- Analyze: {dist.analyze}%\n"
        f"- Evaluate: {dist.evaluate}%\n"
        f"- Create: {dist.create}%"
    )


async def _generate_and_verify(
    num_questions: int,
    course_title: str,
    module_title: str,
    purpose: str,
    difficulty: str,
    answer_type: str,
    topic_weights: list,
    bloom_distribution: Optional[QuizGenBloomsDistribution],
) -> list:
    """Generate questions with AI then verify them. Returns list of dicts."""

    # Step 1: Generate
    messages = compile_prompt(
        QUIZ_TOPIC_GENERATION_SYSTEM_PROMPT,
        QUIZ_TOPIC_GENERATION_USER_PROMPT,
        num_questions=str(num_questions),
        course_title=course_title,
        module_title=module_title,
        purpose=purpose,
        difficulty=difficulty,
        answer_type=answer_type,
        topics_list=_build_topics_list(topic_weights),
        blooms_distribution=_build_blooms_distribution(bloom_distribution),
    )

    llm_output: TopicLLMOutput = await run_llm_with_openai(
        model=openai_plan_to_model_name["text"],
        messages=messages,
        response_model=TopicLLMOutput,
        max_output_tokens=8192,
        api_mode="chat_completions",
    )

    questions = llm_output.questions

    # Step 2: Verify
    questions_json = json.dumps(
        [q.model_dump() for q in questions], indent=2
    )
    verify_messages = compile_prompt(
        QUIZ_TOPIC_VERIFY_SYSTEM_PROMPT,
        QUIZ_TOPIC_VERIFY_USER_PROMPT,
        questions_json=questions_json,
    )

    try:
        verify_output: TopicVerificationOutput = await run_llm_with_openai(
            model=openai_plan_to_model_name["text-mini"],
            messages=verify_messages,
            response_model=TopicVerificationOutput,
            max_output_tokens=4096,
            api_mode="chat_completions",
        )
        verification_map = {r.question_index: r for r in verify_output.results}
    except Exception as e:
        logger.error(f"Verification failed (non-fatal): {e}")
        verification_map = {}

    # Step 3: Merge
    result = []
    for i, q in enumerate(questions):
        ver = verification_map.get(i)
        result.append({
            "id": str(uuid.uuid4()),
            "question_text": q.question_text,
            "topic": q.topic,
            "blooms_level": q.blooms_level,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "difficulty": q.difficulty,
            "question_type": q.question_type,
            "verification_status": ver.status if ver else "pending",
            "verification_reason": ver.reason if ver else "",
        })

    return result


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/", response_model=QuizGenerationResponse)
async def create_quiz_generation(request: CreateQuizGenerationRequest):
    payload_log = {
        "course_title": request.course_title,
        "module_title": request.module_title,
        "purpose": request.purpose.value,
        "length": request.length,
        "difficulty": request.difficulty.value,
        "question_type": request.question_type.value,
        "answer_type": request.answer_type.value,
        "topic_weights": [
            {"keyword": tw.keyword, "weight": tw.weight}
            for tw in request.topic_weights
        ],
        "course_id": request.course_id,
        "org_id": request.org_id,
    }

    print("\n" + "=" * 60)
    print("📥  QUIZ GENERATION REQUEST RECEIVED")
    print("=" * 60)
    print(json.dumps(payload_log, indent=2))
    print("=" * 60 + "\n")
    logger.info(f"Quiz generation request: {payload_log}")

    config = await create_quiz_generation_config(
        course_title=request.course_title,
        module_title=request.module_title,
        purpose=request.purpose.value,
        length=request.length,
        difficulty=request.difficulty.value,
        question_type=request.question_type.value,
        answer_type=request.answer_type.value,
        topic_weights=request.topic_weights,
        course_id=request.course_id,
        org_id=request.org_id,
    )

    print("\n" + "=" * 60)
    print("✅  QUIZ GENERATION CONFIG SAVED  (id={})".format(config["id"]))
    print("=" * 60)
    print(json.dumps(config, indent=2, default=str))
    print("=" * 60 + "\n")
    logger.info(f"Quiz generation config saved: id={config['id']}")

    return QuizGenerationResponse(
        id=config["id"],
        course_title=config["course_title"],
        module_title=config["module_title"],
        purpose=config["purpose"],
        length=config["length"],
        difficulty=config["difficulty"],
        question_type=config["question_type"],
        answer_type=config["answer_type"],
        topic_weights=[TopicWeight(**tw) for tw in config["topic_weights"]],
        course_id=config["course_id"],
        org_id=config["org_id"],
        status=config["status"],
        created_at=str(config["created_at"]),
    )


@router.post("/generate-questions")
async def generate_questions(request: GenerateQuestionsRequest):
    """
    AI generates questions based on topic weights + optional Bloom's distribution.
    Runs a second verification agent and returns questions with status tags.
    """
    print("\n" + "=" * 60)
    print("🤖  GENERATING QUESTIONS")
    print("=" * 60)
    print(f"  topics: {[tw.keyword for tw in request.topic_weights]}")
    print(f"  length: {request.length}  difficulty: {request.difficulty.value}")
    print(f"  blooms: {request.bloom_distribution}")
    print("=" * 60 + "\n")

    try:
        questions = await _generate_and_verify(
            num_questions=request.length,
            course_title=request.course_title,
            module_title=request.module_title,
            purpose=request.purpose.value,
            difficulty=request.difficulty.value,
            answer_type=request.answer_type.value,
            topic_weights=request.topic_weights,
            bloom_distribution=request.bloom_distribution,
        )
    except Exception as e:
        logger.error(f"Question generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

    print("\n" + "=" * 60)
    print(f"✅  GENERATED {len(questions)} QUESTIONS")
    verified = sum(1 for q in questions if q["verification_status"] == "verified")
    wrong = sum(1 for q in questions if q["verification_status"] == "wrong")
    print(f"   verified={verified}  wrong={wrong}  pending={len(questions)-verified-wrong}")
    print("=" * 60 + "\n")

    return {"questions": questions}


@router.post("/regenerate-question")
async def regenerate_question(request: RegenerateQuestionRequest):
    """
    Regenerate a single question for a specific topic (used by 'Spotted Wrong' refresh).
    """
    try:
        single_topic = TopicWeight(keyword=request.topic, weight=100)
        questions = await _generate_and_verify(
            num_questions=1,
            course_title=request.course_title,
            module_title=request.module_title,
            purpose="practice",
            difficulty=request.difficulty.value,
            answer_type=request.answer_type.value,
            topic_weights=[single_topic],
            bloom_distribution=None,  # type: ignore[arg-type]
        )
    except Exception as e:
        logger.error(f"Question regeneration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")

    if not questions:
        raise HTTPException(status_code=500, detail="No question generated")

    return questions[0]


@router.get("/{config_id}", response_model=QuizGenerationResponse)
async def get_quiz_generation(config_id: int):
    config = await get_quiz_generation_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Quiz generation config not found")

    return QuizGenerationResponse(
        id=config["id"],
        course_title=config["course_title"],
        module_title=config["module_title"],
        purpose=config["purpose"],
        length=config["length"],
        difficulty=config["difficulty"],
        question_type=config["question_type"],
        answer_type=config["answer_type"],
        topic_weights=[TopicWeight(**tw) for tw in config["topic_weights"]],
        course_id=config["course_id"],
        org_id=config["org_id"],
        status=config["status"],
        created_at=str(config["created_at"]),
    )
