"""Recruiter MCQ/question generation pipeline.

Orchestrates: parse → classify → (synthesize | extract skills) → weight →
generate (MCQ + code + text) → validate → refine.

All LLM calls use OpenAI via the existing `api.llm.run_llm_with_openai` helper.
"""

import json
from typing import Dict, List, Optional

from api.config import openai_plan_to_model_name
from api.db.recruiter import update_recruiter_generation
from api.llm import run_llm_with_openai
from api.models import (
    ExtractedSkill,
    ExtractedSkillList,
    JDClassification,
    ParsedResume,
    RecruiterDifficulty,
    RecruiterJDType,
    RecruiterQuestion,
    RecruiterQuestionSet,
    RecruiterQuestionType,
    SynthesizedJD,
    ValidatorReport,
    WeightedSkill,
)
from api.prompts import compile_prompt
from api.prompts.recruiter import (
    JD_CLASSIFIER_SYSTEM_PROMPT,
    JD_CLASSIFIER_USER_PROMPT,
    JD_SYNTHESIZE_SYSTEM_PROMPT,
    JD_SYNTHESIZE_USER_PROMPT,
    QUESTION_GENERATOR_SYSTEM_PROMPT,
    QUESTION_GENERATOR_USER_PROMPT,
    QUESTION_VALIDATOR_SYSTEM_PROMPT,
    QUESTION_VALIDATOR_USER_PROMPT,
    RESUME_PARSER_SYSTEM_PROMPT,
    RESUME_PARSER_USER_PROMPT,
    SKILL_EXTRACTION_SYSTEM_PROMPT,
    SKILL_EXTRACTION_USER_PROMPT,
)
from api.utils.logging import logger


TEXT_MODEL = openai_plan_to_model_name["text"]
MINI_MODEL = openai_plan_to_model_name["text-mini"]

MAX_REGEN_PASSES = 2


# ---------------------------------------------------------------------------
# Stage 1: JD classification
# ---------------------------------------------------------------------------

async def classify_jd(jd_text: str) -> JDClassification:
    messages = compile_prompt(
        JD_CLASSIFIER_SYSTEM_PROMPT,
        JD_CLASSIFIER_USER_PROMPT,
        jd_text=jd_text,
    )
    return await run_llm_with_openai(
        model=MINI_MODEL,
        messages=messages,
        response_model=JDClassification,
        max_output_tokens=1024,
    )


# ---------------------------------------------------------------------------
# Stage 2a: JD synthesis from short intent + skills (unstructured path)
# ---------------------------------------------------------------------------

async def synthesize_jd(intent: str, skills: List[str]) -> SynthesizedJD:
    messages = compile_prompt(
        JD_SYNTHESIZE_SYSTEM_PROMPT,
        JD_SYNTHESIZE_USER_PROMPT,
        intent=intent or "(not provided)",
        skills=", ".join(skills) if skills else "(none)",
    )
    return await run_llm_with_openai(
        model=TEXT_MODEL,
        messages=messages,
        response_model=SynthesizedJD,
        max_output_tokens=2048,
    )


def synthesized_jd_to_text(jd: SynthesizedJD) -> str:
    parts = [
        f"Title: {jd.title}",
        "",
        jd.description,
        "",
        "Responsibilities:",
    ]
    parts.extend(f"- {r}" for r in jd.responsibilities)
    parts.append("")
    parts.append("Required Skills: " + ", ".join(jd.required_skills))
    if jd.nice_to_have:
        parts.append("Nice to have: " + ", ".join(jd.nice_to_have))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Stage 2b: Skill extraction from structured JD
# ---------------------------------------------------------------------------

async def extract_skills_from_jd(jd_text: str) -> List[ExtractedSkill]:
    messages = compile_prompt(
        SKILL_EXTRACTION_SYSTEM_PROMPT,
        SKILL_EXTRACTION_USER_PROMPT,
        jd_text=jd_text,
    )
    result = await run_llm_with_openai(
        model=MINI_MODEL,
        messages=messages,
        response_model=ExtractedSkillList,
        max_output_tokens=1536,
    )
    return result.skills


# ---------------------------------------------------------------------------
# Stage 3: Resume parser (Flow C)
# ---------------------------------------------------------------------------

async def parse_resume(resume_text: str) -> ParsedResume:
    messages = compile_prompt(
        RESUME_PARSER_SYSTEM_PROMPT,
        RESUME_PARSER_USER_PROMPT,
        resume_text=resume_text,
    )
    return await run_llm_with_openai(
        model=MINI_MODEL,
        messages=messages,
        response_model=ParsedResume,
        max_output_tokens=2048,
    )


# ---------------------------------------------------------------------------
# Stage 4: Weighting
# ---------------------------------------------------------------------------

def _normalize(weights: List[WeightedSkill]) -> List[WeightedSkill]:
    total = sum(w.weight for w in weights) or 1.0
    return [WeightedSkill(skill=w.skill, weight=w.weight / total) for w in weights]


def focus_weights_for_budget(
    weights: List[WeightedSkill], num_questions: int
) -> List[WeightedSkill]:
    """Keep only the highest-weight skills up to the question budget.

    The generator/validator both work far better when `len(skills) <= num_questions`,
    otherwise skills get spread so thin that half the JD looks uncovered.
    We cap at `num_questions` (minimum 3 skills) and re-normalize.
    """
    if not weights:
        return weights
    cap = max(3, min(len(weights), num_questions))
    sorted_w = sorted(weights, key=lambda w: w.weight, reverse=True)
    trimmed = sorted_w[:cap]
    return _normalize(trimmed)


def default_weights_from_skills(skills: List[ExtractedSkill]) -> List[WeightedSkill]:
    if not skills:
        return []
    weighted = [
        WeightedSkill(skill=s.name, weight=float(max(1, min(5, s.importance))))
        for s in skills
    ]
    return _normalize(weighted)


def weights_from_plain_skill_list(skills: List[str]) -> List[WeightedSkill]:
    if not skills:
        return []
    return _normalize([WeightedSkill(skill=s, weight=1.0) for s in skills])


def compute_gap_weights(
    jd_skills: List[ExtractedSkill],
    resume_skills: List,
) -> List[WeightedSkill]:
    """JD skill weights adjusted by inverse of resume proficiency (gap emphasis).

    0.2 floor keeps already-known skills partially covered so we still validate them.
    """
    if not jd_skills:
        return []

    rmap = {s.name.lower(): s.proficiency for s in (resume_skills or [])}
    out: List[WeightedSkill] = []
    for s in jd_skills:
        prof = rmap.get(s.name.lower(), 0.0)
        # Fuzzy contains match
        if prof == 0.0:
            for rname, rprof in rmap.items():
                if rname in s.name.lower() or s.name.lower() in rname:
                    prof = max(prof, rprof)
        gap = 1.0 - max(0.0, min(1.0, prof))
        importance = float(max(1, min(5, s.importance)))
        out.append(WeightedSkill(skill=s.name, weight=importance * (0.2 + 0.8 * gap)))
    return _normalize(out)


# ---------------------------------------------------------------------------
# Stage 5: Question generation
# ---------------------------------------------------------------------------

def _format_weighted_skills(weights: List[WeightedSkill]) -> str:
    if not weights:
        return "(none)"
    return "\n".join(f"- {w.skill} : {w.weight:.2f}" for w in weights)


def _format_type_mix(type_mix: Dict[RecruiterQuestionType, int]) -> str:
    parts = []
    for t, n in type_mix.items():
        key = t.value if hasattr(t, "value") else str(t)
        parts.append(f"{key}: {n}")
    return ", ".join(parts)


async def generate_questions(
    grounding_text: str,
    weighted_skills: List[WeightedSkill],
    num_questions: int,
    difficulty: RecruiterDifficulty,
    type_mix: Dict[RecruiterQuestionType, int],
    candidate_summary: Optional[str] = None,
) -> List[RecruiterQuestion]:
    candidate_section = ""
    if candidate_summary:
        candidate_section = (
            "CANDIDATE PROFILE (tailor the questions to probe gaps and validate strengths):\n"
            f"{candidate_summary}\n"
        )

    messages = compile_prompt(
        QUESTION_GENERATOR_SYSTEM_PROMPT,
        QUESTION_GENERATOR_USER_PROMPT,
        num_questions=str(num_questions),
        grounding_text=grounding_text,
        weighted_skills=_format_weighted_skills(weighted_skills),
        type_mix=_format_type_mix(type_mix),
        difficulty=difficulty.value if hasattr(difficulty, "value") else str(difficulty),
        candidate_section=candidate_section,
    )
    result = await run_llm_with_openai(
        model=TEXT_MODEL,
        messages=messages,
        response_model=RecruiterQuestionSet,
        max_output_tokens=6000,
    )
    return result.questions


# ---------------------------------------------------------------------------
# Stage 6: Validator
# ---------------------------------------------------------------------------

async def validate_questions(
    grounding_text: str,
    weighted_skills: List[WeightedSkill],
    questions: List[RecruiterQuestion],
) -> ValidatorReport:
    questions_json = json.dumps(
        [q.model_dump() for q in questions], indent=2
    )
    messages = compile_prompt(
        QUESTION_VALIDATOR_SYSTEM_PROMPT,
        QUESTION_VALIDATOR_USER_PROMPT,
        num_questions=str(len(questions)),
        grounding_text=grounding_text,
        weighted_skills=_format_weighted_skills(weighted_skills),
        questions_json=questions_json,
    )
    return await run_llm_with_openai(
        model=MINI_MODEL,
        messages=messages,
        response_model=ValidatorReport,
        max_output_tokens=1536,
    )


async def generate_and_validate(
    grounding_text: str,
    weighted_skills: List[WeightedSkill],
    num_questions: int,
    difficulty: RecruiterDifficulty,
    type_mix: Dict[RecruiterQuestionType, int],
    candidate_summary: Optional[str] = None,
):
    questions = await generate_questions(
        grounding_text=grounding_text,
        weighted_skills=weighted_skills,
        num_questions=num_questions,
        difficulty=difficulty,
        type_mix=type_mix,
        candidate_summary=candidate_summary,
    )

    for attempt in range(MAX_REGEN_PASSES):
        report = await validate_questions(grounding_text, weighted_skills, questions)
        if report.ok:
            return questions, report

        logger.info(
            f"Recruiter validator flagged attempt {attempt + 1}: issues={report.issues}"
        )

        # Partial regeneration: only replace flagged questions. If the validator
        # didn't pinpoint indices but marked not-ok, regenerate the whole set once.
        if report.questions_to_regenerate:
            # Regenerate only the flagged count
            regen_count = len(report.questions_to_regenerate)
            replacements = await generate_questions(
                grounding_text=grounding_text,
                weighted_skills=weighted_skills,
                num_questions=regen_count,
                difficulty=difficulty,
                type_mix=type_mix,
                candidate_summary=candidate_summary,
            )
            for idx, new_q in zip(report.questions_to_regenerate, replacements):
                if 0 <= idx < len(questions):
                    questions[idx] = new_q
        else:
            questions = await generate_questions(
                grounding_text=grounding_text,
                weighted_skills=weighted_skills,
                num_questions=num_questions,
                difficulty=difficulty,
                type_mix=type_mix,
                candidate_summary=candidate_summary,
            )

    # Final report after last attempt (even if not ok, return best-effort set)
    final_report = await validate_questions(grounding_text, weighted_skills, questions)
    return questions, final_report


# ---------------------------------------------------------------------------
# High-level flows — each persists progress to the DB so the frontend can poll
# ---------------------------------------------------------------------------

async def run_from_suggested_flow(
    gen_id: int,
    jd_title: str,
    jd_description: str,
    jd_responsibilities: List[str],
    jd_skills: List[str],
    num_questions: int,
    difficulty: RecruiterDifficulty,
    type_mix: Dict[RecruiterQuestionType, int],
):
    """Flow A — the recruiter picked a suggested JD. It's already structured."""
    try:
        jd_text = (
            f"Title: {jd_title}\n\n"
            f"{jd_description}\n\n"
            "Responsibilities:\n"
            + "\n".join(f"- {r}" for r in jd_responsibilities)
            + "\n\nRequired Skills: "
            + ", ".join(jd_skills)
        )

        await update_recruiter_generation(
            gen_id,
            status="extracting_skills",
            jd_type=RecruiterJDType.structured.value,
            jd_text=jd_text,
        )

        extracted = await extract_skills_from_jd(jd_text)
        # Merge with the JD-provided skill list to guarantee coverage
        existing_names = {s.name.lower() for s in extracted}
        for s in jd_skills or []:
            if s.lower() not in existing_names:
                extracted.append(ExtractedSkill(name=s, category="other", importance=3))

        weights = default_weights_from_skills(extracted)
        weights = focus_weights_for_budget(weights, num_questions)

        await update_recruiter_generation(
            gen_id,
            status="generating",
            extracted_skills=[s.model_dump() for s in extracted],
            weighted_skills=[w.model_dump() for w in weights],
        )

        questions, report = await generate_and_validate(
            grounding_text=jd_text,
            weighted_skills=weights,
            num_questions=num_questions,
            difficulty=difficulty,
            type_mix=type_mix,
        )

        await update_recruiter_generation(
            gen_id,
            status="done",
            questions=[q.model_dump() for q in questions],
            validator_report=report.model_dump(),
        )
    except Exception as e:
        logger.exception("Recruiter suggested flow failed")
        await update_recruiter_generation(gen_id, status="failed", error=str(e))


async def run_own_jd_classification(gen_id: int, jd_text: str):
    """Flow B phase 1 — parse + classify + (maybe) synthesize.

    If unstructured, persists a synthesized pseudo-JD and waits for user
    confirmation (status=awaiting_confirmation). If structured, proceeds to
    skill extraction and stores that for the generation step.
    """
    try:
        await update_recruiter_generation(gen_id, status="classifying", jd_text=jd_text)
        classification = await classify_jd(jd_text)

        if classification.type == RecruiterJDType.unstructured:
            await update_recruiter_generation(gen_id, status="synthesizing")
            synthesized = await synthesize_jd(
                intent=jd_text,
                skills=classification.extracted_skills,
            )
            await update_recruiter_generation(
                gen_id,
                status="awaiting_confirmation",
                jd_type=RecruiterJDType.unstructured.value,
                synthesized_jd=synthesized.model_dump(),
            )
            return

        # structured -> extract and keep weights for generation step
        await update_recruiter_generation(
            gen_id,
            status="extracting_skills",
            jd_type=RecruiterJDType.structured.value,
        )
        extracted = await extract_skills_from_jd(jd_text)
        weights = default_weights_from_skills(extracted)
        await update_recruiter_generation(
            gen_id,
            status="awaiting_confirmation",
            extracted_skills=[s.model_dump() for s in extracted],
            weighted_skills=[w.model_dump() for w in weights],
        )
    except Exception as e:
        logger.exception("Recruiter own-JD classification failed")
        await update_recruiter_generation(gen_id, status="failed", error=str(e))


async def run_jd_resume_classification(
    gen_id: int,
    jd_text: str,
    resume_text: str,
):
    """Flow C phase 1 — same as flow B plus resume parsing."""
    try:
        await update_recruiter_generation(
            gen_id,
            status="classifying",
            jd_text=jd_text,
            resume_text=resume_text,
        )
        classification = await classify_jd(jd_text)
        parsed_resume = await parse_resume(resume_text)

        if classification.type == RecruiterJDType.unstructured:
            await update_recruiter_generation(gen_id, status="synthesizing")
            synthesized = await synthesize_jd(
                intent=jd_text,
                skills=classification.extracted_skills,
            )
            # Build temporary structured skills from synthesized.required_skills
            tmp_extracted = [
                ExtractedSkill(name=s, category="other", importance=4)
                for s in synthesized.required_skills
            ]
            weights = compute_gap_weights(tmp_extracted, parsed_resume.skills)
            await update_recruiter_generation(
                gen_id,
                status="awaiting_confirmation",
                jd_type=RecruiterJDType.unstructured.value,
                synthesized_jd=synthesized.model_dump(),
                extracted_skills=[s.model_dump() for s in tmp_extracted],
                weighted_skills=[w.model_dump() for w in weights],
            )
            return

        # structured
        await update_recruiter_generation(
            gen_id,
            status="extracting_skills",
            jd_type=RecruiterJDType.structured.value,
        )
        extracted = await extract_skills_from_jd(jd_text)
        weights = compute_gap_weights(extracted, parsed_resume.skills)
        await update_recruiter_generation(
            gen_id,
            status="awaiting_confirmation",
            extracted_skills=[s.model_dump() for s in extracted],
            weighted_skills=[w.model_dump() for w in weights],
        )
    except Exception as e:
        logger.exception("Recruiter JD+resume classification failed")
        await update_recruiter_generation(gen_id, status="failed", error=str(e))


async def run_generation_after_confirmation(
    gen_id: int,
    record: dict,
    num_questions: int,
    difficulty: RecruiterDifficulty,
    type_mix: Dict[RecruiterQuestionType, int],
    candidate_summary: Optional[str] = None,
    override_grounding_text: Optional[str] = None,
):
    """Phase 2 for flows B/C — actually generate the questions after the
    recruiter has confirmed the (possibly synthesized) JD.
    """
    try:
        await update_recruiter_generation(gen_id, status="generating")

        if override_grounding_text:
            grounding_text = override_grounding_text
        elif record.get("synthesized_jd"):
            synth = SynthesizedJD(**record["synthesized_jd"])
            grounding_text = synthesized_jd_to_text(synth)
        else:
            grounding_text = record.get("jd_text") or ""

        weighted_raw = record.get("weighted_skills") or []
        weights = [WeightedSkill(**w) for w in weighted_raw]
        if not weights:
            extracted_raw = record.get("extracted_skills") or []
            extracted = [ExtractedSkill(**s) for s in extracted_raw]
            weights = default_weights_from_skills(extracted)

        # Focus weights on the top-N skills for the budget we actually have —
        # otherwise a JD with 25 skills and 10 questions ends up with huge gaps.
        weights = focus_weights_for_budget(weights, num_questions)

        questions, report = await generate_and_validate(
            grounding_text=grounding_text,
            weighted_skills=weights,
            num_questions=num_questions,
            difficulty=difficulty,
            type_mix=type_mix,
            candidate_summary=candidate_summary,
        )

        await update_recruiter_generation(
            gen_id,
            status="done",
            questions=[q.model_dump() for q in questions],
            validator_report=report.model_dump(),
        )
    except Exception as e:
        logger.exception("Recruiter generation-after-confirmation failed")
        await update_recruiter_generation(gen_id, status="failed", error=str(e))
