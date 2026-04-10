import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, List, Dict, Optional
from pydantic import BaseModel, Field

from api.llm import stream_llm_with_openai, run_llm_with_openai
from api.db.course import get_course as get_course_from_db
from api.db.task import get_task
from api.db.utils import construct_description_from_blocks
from api.models import (
    BloomsGenerateRequest,
    BloomsAssessmentOutput,
    GeneratedBloomsQuestion,
    BloomsVerifyRequest,
    ScenarioGenerateRequest,
    ScenarioAssessmentOutput,
    GeneratedScenarioQuestion,
    ScenarioVerifyRequest,
    TaskType,
)
from api.prompts import compile_prompt
from api.prompts.blooms_taxonomy import BLOOMS_SYSTEM_PROMPT, BLOOMS_USER_PROMPT
from api.prompts.scenario_mode import SCENARIO_SYSTEM_PROMPT, SCENARIO_USER_PROMPT
from api.config import openai_plan_to_model_name
from api.utils.logging import logger

router = APIRouter()


# ============================================================
# Pydantic response models for LLM structured output
# ============================================================

class LLMGeneratedQuestion(BaseModel):
    question_text: str = Field(description="The full text of the question")
    blooms_level: str = Field(
        description="The Bloom's Taxonomy level: remember, understand, apply, analyze, evaluate, or create"
    )
    options: Optional[List[str]] = Field(
        default=None,
        description="For objective/MCQ questions: exactly 4 answer options. For subjective: null.",
    )
    correct_answer: str = Field(
        description="The correct answer text. For MCQ, this must exactly match one of the options."
    )
    explanation: str = Field(
        description="A brief explanation of why the correct answer is correct."
    )
    source_reference: str = Field(
        description="Which section/topic of the learning material this question is derived from."
    )
    difficulty: str = Field(description="easy, medium, or hard")
    question_type: str = Field(description="objective or subjective")


class LLMAssessmentOutput(BaseModel):
    questions: List[LLMGeneratedQuestion] = Field(
        description="The list of generated assessment questions"
    )


class VerificationResult(BaseModel):
    question_index: int = Field(description="The 0-based index of the question being verified")
    status: str = Field(
        description="verified, warning, or wrong"
    )
    reason: str = Field(
        description="Explanation for the verification status. If verified, say 'Question is valid'. If wrong, explain the issue."
    )
    correct_answer_suggestion: Optional[str] = Field(
        default=None,
        description="If the original correct answer is wrong, suggest the actual correct answer.",
    )


class VerificationOutput(BaseModel):
    results: List[VerificationResult] = Field(
        description="Verification results for each question"
    )


# ============================================================
# Helper: Extract learning material content from a module
# ============================================================

async def get_module_learning_content(
    course_id: int, milestone_id: int, task_id: Optional[int] = None
) -> str:
    """
    Fetches all learning material text from a specific milestone (module) in a course.
    If task_id is provided, only that specific task's content is used.
    """
    if task_id:
        # Get a specific learning material task
        task_data = await get_task(task_id)
        if not task_data:
            raise HTTPException(status_code=404, detail="Task not found")
        if task_data["type"] != TaskType.LEARNING_MATERIAL:
            raise HTTPException(
                status_code=400, detail="Task is not a learning material"
            )
        return construct_description_from_blocks(task_data["blocks"])

    # Get all learning material from the milestone
    course = await get_course_from_db(course_id, only_published=False)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Find the target milestone
    target_milestone = None
    for milestone in course.get("milestones", []):
        if milestone["id"] == milestone_id:
            target_milestone = milestone
            break

    if not target_milestone:
        raise HTTPException(status_code=404, detail="Milestone/module not found")

    # Collect all learning material tasks in this milestone
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
            detail="No learning material content found in this module. Please add learning materials first.",
        )

    return "\n\n---\n\n".join(content_parts)


# ============================================================
# Route: Extract content from a module (preview for trainer)
# ============================================================

@router.post("/extract-content")
async def extract_module_content(course_id: int, milestone_id: int):
    """
    Extracts and returns the text content of all learning materials in a module.
    Used by the frontend to preview what the AI will read before generating.
    """
    content = await get_module_learning_content(course_id, milestone_id)

    # Also return the course structure for context
    course = await get_course_from_db(course_id, only_published=False)
    milestones_info = []
    for m in course.get("milestones", []):
        lm_count = sum(
            1 for t in m.get("tasks", []) if t["type"] == TaskType.LEARNING_MATERIAL
        )
        milestones_info.append(
            {
                "id": m["id"],
                "name": m["name"],
                "learning_material_count": lm_count,
            }
        )

    return {
        "content": content,
        "content_length": len(content),
        "milestones": milestones_info,
    }


# ============================================================
# Route: Generate Bloom's Taxonomy Assessment (Streaming)
# ============================================================

@router.post("/generate-blooms")
async def generate_blooms_assessment(request: BloomsGenerateRequest):
    """
    Generates quiz questions tagged with Bloom's Taxonomy levels from module content.
    Streams the response back to the frontend as NDJSON for real-time rendering.
    """

    # 1. Extract learning material content
    content = await get_module_learning_content(
        request.course_id, request.milestone_id, request.task_id
    )

    logger.info(
        f"Generating Bloom's assessment: {request.num_questions} questions, "
        f"difficulty={request.difficulty}, from {len(content)} chars of content"
    )

    # 2. Calculate actual question counts from percentages
    dist = request.bloom_distribution
    total_pct = dist.remember + dist.understand + dist.apply + dist.analyze + dist.evaluate + dist.create

    # Normalize if percentages don't sum to 100
    if total_pct != 100 and total_pct > 0:
        factor = 100 / total_pct
        dist.remember = int(dist.remember * factor)
        dist.understand = int(dist.understand * factor)
        dist.apply = int(dist.apply * factor)
        dist.analyze = int(dist.analyze * factor)
        dist.evaluate = int(dist.evaluate * factor)
        dist.create = 100 - dist.remember - dist.understand - dist.apply - dist.analyze - dist.evaluate

    # 3. Build the prompt
    question_types_str = ", ".join(request.question_types)
    messages = compile_prompt(
        BLOOMS_SYSTEM_PROMPT,
        BLOOMS_USER_PROMPT,
        learning_material_content=content,
        num_questions=str(request.num_questions),
        remember_pct=str(dist.remember),
        understand_pct=str(dist.understand),
        apply_pct=str(dist.apply),
        analyze_pct=str(dist.analyze),
        evaluate_pct=str(dist.evaluate),
        create_pct=str(dist.create),
        difficulty=request.difficulty,
        question_types=question_types_str,
    )

    # 4. Stream the LLM response
    async def stream_generation() -> AsyncGenerator[str, None]:
        try:
            async for chunk in stream_llm_with_openai(
                model=openai_plan_to_model_name["text"],
                messages=messages,
                response_model=LLMAssessmentOutput,
                max_output_tokens=8192,
            ):
                if chunk and hasattr(chunk, "model_dump"):
                    yield json.dumps(chunk.model_dump()) + "\n"
        except Exception as e:
            # Known OpenAI SDK issue: AsyncStream object has no attribute 'aclose'
            if str(e) == "'AsyncStream' object has no attribute 'aclose'":
                # Silently end - the stream has already completed successfully
                pass
            else:
                logger.error(f"Error generating Bloom's assessment: {e}")
                error_payload = {"error": str(e)}
                yield json.dumps(error_payload) + "\n"

    return StreamingResponse(
        stream_generation(),
        media_type="application/x-ndjson",
    )


# ============================================================
# Route: Verify generated questions with a second AI agent
# ============================================================

VERIFY_SYSTEM_PROMPT = """You are an Assessment Quality Assurance expert. You receive a list of generated quiz questions 
and the original learning material they were derived from.

For EACH question, verify:
1. **Factual Accuracy**: Is the correct answer actually correct based on the learning material?
2. **Option Quality** (for MCQs): Are the distractor options plausible but definitely incorrect? Are there accidentally TWO correct answers?
3. **Bloom's Level Accuracy**: Does the question actually test the claimed Bloom's Taxonomy level?
4. **Source Alignment**: Is the question actually derivable from the provided learning material, or is it hallucinated?
5. **Clarity**: Is the question clear and unambiguous?

Return a verification result for EACH question with status:
- "verified" — The question passes all checks.
- "warning" — The question has minor issues but is usable (e.g., slightly ambiguous).
- "wrong" — The question has critical issues (wrong answer, two correct options, hallucinated content).

Include a clear reason for every status."""

VERIFY_USER_PROMPT = """Original Learning Material:
<learning_material>
{{learning_material_content}}
</learning_material>

Questions to verify:
<questions>
{{questions_json}}
</questions>

Verify each question and return results."""


@router.post("/verify-questions")
async def verify_generated_questions(request: BloomsVerifyRequest):
    """
    Runs Agent 2 (The Validator) on generated questions.
    Checks for hallucinations, wrong answers, option issues, and Bloom's level accuracy.
    """
    questions_json = json.dumps(
        [q.model_dump() for q in request.questions], indent=2
    )

    messages = compile_prompt(
        VERIFY_SYSTEM_PROMPT,
        VERIFY_USER_PROMPT,
        learning_material_content=request.learning_material_content,
        questions_json=questions_json,
    )

    try:
        result = await run_llm_with_openai(
            model=openai_plan_to_model_name["text-mini"],
            messages=messages,
            response_model=VerificationOutput,
            max_output_tokens=4096,
        )
        return result.model_dump()
    except Exception as e:
        logger.error(f"Error verifying questions: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")


# ============================================================
# Scenario Mode: Pydantic models for LLM structured output
# ============================================================

class LLMScenarioQuestion(BaseModel):
    question_text: str = Field(description="The question text, set in the context of the scenario")
    options: Optional[List[str]] = Field(
        default=None,
        description="For objective/MCQ questions: exactly 4 answer options. For subjective: null.",
    )
    correct_answer: str = Field(
        description="The correct answer text. For MCQ, this must exactly match one of the options."
    )
    explanation: str = Field(
        description="Explanation connecting the correct answer back to both the scenario AND the underlying concept."
    )
    concept_tested: str = Field(
        description="Which concept from the learning material this question tests."
    )
    difficulty: str = Field(description="easy, medium, or hard")
    question_type: str = Field(description="objective or subjective")


class LLMScenarioOutput(BaseModel):
    scenario_title: str = Field(
        description="A short, catchy title for the scenario (e.g., 'The Server Meltdown at TechCorp')"
    )
    scenario_narrative: str = Field(
        description="A 2-4 paragraph compelling scenario narrative that contextualizes the learning material concepts in a realistic situation."
    )
    questions: List[LLMScenarioQuestion] = Field(
        description="The list of generated scenario-based questions"
    )


class ScenarioVerificationResult(BaseModel):
    question_index: int = Field(description="The 0-based index of the question being verified")
    status: str = Field(description="verified, warning, or wrong")
    reason: str = Field(
        description="Explanation for the verification status."
    )
    correct_answer_suggestion: Optional[str] = Field(
        default=None,
        description="If the original correct answer is wrong, suggest the actual correct answer.",
    )


class ScenarioVerificationOutput(BaseModel):
    results: List[ScenarioVerificationResult] = Field(
        description="Verification results for each question"
    )


# ============================================================
# Route: Generate Scenario-Based Assessment (Streaming)
# ============================================================

@router.post("/generate-scenario")
async def generate_scenario_assessment(request: ScenarioGenerateRequest):
    """
    Generates a scenario narrative + questions from module content.
    Streams the response back as NDJSON for real-time rendering.
    """

    # 1. Extract learning material content
    content = await get_module_learning_content(
        request.course_id, request.milestone_id, request.task_id
    )

    logger.info(
        f"Generating scenario assessment: {request.num_questions} questions, "
        f"difficulty={request.difficulty}, "
        f"from {len(content)} chars of content"
    )

    # 2. Build the prompt
    question_types_str = ", ".join(request.question_types)
    messages = compile_prompt(
        SCENARIO_SYSTEM_PROMPT,
        SCENARIO_USER_PROMPT,
        learning_material_content=content,
        num_questions=str(request.num_questions),
        difficulty=request.difficulty,
        question_types=question_types_str,
    )

    # 3. Stream the LLM response
    async def stream_generation() -> AsyncGenerator[str, None]:
        try:
            async for chunk in stream_llm_with_openai(
                model=openai_plan_to_model_name["text"],
                messages=messages,
                response_model=LLMScenarioOutput,
                max_output_tokens=8192,
            ):
                if chunk and hasattr(chunk, "model_dump"):
                    yield json.dumps(chunk.model_dump()) + "\n"
        except Exception as e:
            if str(e) == "'AsyncStream' object has no attribute 'aclose'":
                pass
            else:
                logger.error(f"Error generating scenario assessment: {e}")
                error_payload = {"error": str(e)}
                yield json.dumps(error_payload) + "\n"

    return StreamingResponse(
        stream_generation(),
        media_type="application/x-ndjson",
    )


# ============================================================
# Route: Verify scenario-based questions with a second AI agent
# ============================================================

SCENARIO_VERIFY_SYSTEM_PROMPT = """You are a Scenario-Based Assessment Quality Assurance expert. You verify quiz questions
that were generated within a specific scenario context.

For EACH question, verify:
1. **Scenario Relevance**: Does the question genuinely relate to the scenario, or is it a generic textbook question?
2. **Factual Accuracy**: Is the correct answer actually correct based on the learning material?
3. **Option Quality** (for MCQs): Are the distractor options plausible within the scenario? Are there accidentally TWO correct answers?
4. **Concept Testing**: Does the question actually test the claimed concept from the learning material?
5. **Clarity**: Is the question clear and unambiguous in the scenario context?

Return a verification result for EACH question with status:
- "verified" — The question passes all checks.
- "warning" — The question has minor issues but is usable.
- "wrong" — The question has critical issues.

Include a clear reason for every status."""

SCENARIO_VERIFY_USER_PROMPT = """Original Learning Material:
<learning_material>
{{learning_material_content}}
</learning_material>

Scenario Narrative:
<scenario>
{{scenario_narrative}}
</scenario>

Questions to verify:
<questions>
{{questions_json}}
</questions>

Verify each question and return results."""


@router.post("/verify-scenario-questions")
async def verify_scenario_questions(request: ScenarioVerifyRequest):
    """
    Runs the Validator agent on scenario-based questions.
    Checks for scenario relevance, factual accuracy, and concept alignment.
    """
    questions_json = json.dumps(
        [q.model_dump() for q in request.questions], indent=2
    )

    messages = compile_prompt(
        SCENARIO_VERIFY_SYSTEM_PROMPT,
        SCENARIO_VERIFY_USER_PROMPT,
        learning_material_content=request.learning_material_content,
        scenario_narrative=request.scenario_narrative,
        questions_json=questions_json,
    )

    try:
        result = await run_llm_with_openai(
            model=openai_plan_to_model_name["text-mini"],
            messages=messages,
            response_model=ScenarioVerificationOutput,
            max_output_tokens=4096,
        )
        return result.model_dump()
    except Exception as e:
        logger.error(f"Error verifying scenario questions: {e}")
        raise HTTPException(status_code=500, detail=f"Verification failed: {str(e)}")
