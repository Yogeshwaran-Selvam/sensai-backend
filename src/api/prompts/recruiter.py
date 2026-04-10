"""Prompts for the recruiter MCQ/Code/Text-question generation workflow."""


# -----------------------------------------------------------------------------
# 1. JD classifier: structured vs unstructured
# -----------------------------------------------------------------------------

JD_CLASSIFIER_SYSTEM_PROMPT = """You are an expert at analyzing job descriptions for a recruiting platform.

Classify the given input as either STRUCTURED or UNSTRUCTURED:

- STRUCTURED: Contains clear sections (role, responsibilities, requirements, skills),
  or has more than ~100 words describing the role, expectations and stack in detail.
- UNSTRUCTURED: Short free-text intent like "I want a React developer and an AWS engineer",
  a single sentence or bullet listing skills with little or no surrounding context.

Also extract the technical skills, tools, frameworks or domain topics mentioned or strongly implied.

Return JSON with:
- type: "structured" or "unstructured"
- confidence: float between 0 and 1
- extracted_skills: list of short skill strings (e.g., ["React", "AWS", "TypeScript"])
- inferred_role: a short role title guessed from the content (e.g., "Full-stack React + AWS Engineer")
- reason: one sentence explaining why this classification was chosen"""

JD_CLASSIFIER_USER_PROMPT = """Classify the following job description input:

---
{{jd_text}}
---"""


# -----------------------------------------------------------------------------
# 2. JD synthesis from skills (used when JD is unstructured)
# -----------------------------------------------------------------------------

JD_SYNTHESIZE_SYSTEM_PROMPT = """You are an expert technical recruiter and job description writer.

Given a short recruiter intent and a list of skills, expand it into a realistic,
detailed job description that can be used to generate assessment questions.

Guidelines:
- Title: a concrete role title matching the skills.
- Description: 2-4 sentences describing the role and seniority.
- Responsibilities: 5-7 bullet points grounded in the provided skills.
- Required skills: expand the skill list with clearly related tools/concepts a candidate would need.
- Nice to have: 2-4 related skills.
- Do NOT invent unrelated domains — stay tightly scoped to the provided skills.
- Output only the structured JD fields."""

JD_SYNTHESIZE_USER_PROMPT = """Recruiter intent:
{{intent}}

Skills to build the JD around:
{{skills}}

Generate a realistic job description suitable for assessing candidates."""


# -----------------------------------------------------------------------------
# 3. Skill extraction from a structured JD
# -----------------------------------------------------------------------------

SKILL_EXTRACTION_SYSTEM_PROMPT = """You are an expert at parsing job descriptions and identifying the technical skills that a candidate must be assessed on.

Given the full text of a job description, return the canonical list of skills.

Guidelines:
- Use canonical names ("JavaScript" not "JS", "PostgreSQL" not "Postgres").
- Each skill has a category: one of ["language", "framework", "tool", "cloud", "database", "concept", "soft", "other"].
- Importance: integer 1-5 reflecting how central the skill is to the role (5 = must-have / core, 1 = nice-to-have).
- Only include skills actually grounded in the JD text. Do not invent.
- Deduplicate aggressively."""

SKILL_EXTRACTION_USER_PROMPT = """Extract the skills required by this job description:

---
{{jd_text}}
---"""


# -----------------------------------------------------------------------------
# 4. Resume parsing (Flow C)
# -----------------------------------------------------------------------------

RESUME_PARSER_SYSTEM_PROMPT = """You are an expert at parsing resumes/CVs for technical recruiting.

Extract structured information from the resume.

Guidelines:
- skills: list of canonical skill names the candidate demonstrates experience with.
  For each, estimate proficiency from 0.0 to 1.0 based on years of experience, project context, seniority of mentions.
- total_experience_years: integer best estimate of total professional experience.
- summary: 2-3 sentence summary of the candidate.
- highlights: 3-5 bullet points of the most relevant technical achievements.
- Be conservative: if a skill is only listed without context, set proficiency around 0.4.
  If used in multiple projects or with years, 0.7+. If clearly senior/lead, 0.9+."""

RESUME_PARSER_USER_PROMPT = """Parse the following resume:

---
{{resume_text}}
---"""


# -----------------------------------------------------------------------------
# 5. Question generator (MCQ + code + text) grounded in JD (+ optional resume)
# -----------------------------------------------------------------------------

QUESTION_GENERATOR_SYSTEM_PROMPT = """You are an expert technical interviewer creating an assessment tailored to a specific job description.

You will generate a mix of question types to evaluate a candidate:
- mcq: multiple choice with exactly 4 options and a single correct answer.
- code: coding question (prompt + starter_code if relevant + expected_solution and a short rationale).
- text: short-answer / conceptual question with an expected_answer describing the ideal response.

Rules:
- Ground every question in the provided JD context. Never ask about unrelated topics.
- Distribute questions roughly according to the provided weighted skill list.
  Higher-weight skills must get proportionally more questions.
- Cover the requested difficulty mix evenly (easy/medium/hard).
- Every question must include: type, skill (matching one in the weighted list), difficulty, bloom_level
  (remember|understand|apply|analyze|evaluate|create), question, and the type-specific answer fields.
- For mcq: options has length 4, correct_index is the 0-based index of the correct option, and the
  other options are plausible distractors, not obviously wrong.
- For code: include language (python/javascript/typescript/java/sql/etc.), a clear problem statement,
  optional starter_code, and expected_solution (reference implementation).
- For text: expected_answer is the rubric / ideal response, 2-5 sentences.
- Do NOT leak the answer inside the question stem.
- Return exactly the requested number of questions."""

QUESTION_GENERATOR_USER_PROMPT = """Generate {{num_questions}} assessment questions for the following role.

JOB DESCRIPTION / GROUNDING:
---
{{grounding_text}}
---

WEIGHTED SKILLS (skill : weight — higher means more questions):
{{weighted_skills}}

QUESTION TYPE MIX REQUESTED: {{type_mix}}
DIFFICULTY: {{difficulty}}

{{candidate_section}}

Return a list of questions respecting the counts and weights above."""


# -----------------------------------------------------------------------------
# 6. Validator agent (second pass)
# -----------------------------------------------------------------------------

QUESTION_VALIDATOR_SYSTEM_PROMPT = """You are a senior technical reviewer validating an auto-generated assessment.

Your job is to check per-question quality and overall balance — NOT to demand exhaustive skill coverage when the question budget is smaller than the skill list.

Per-question checks:
- Groundedness: answerable from the JD context and general knowledge of the skill.
- Correctness: for MCQs, confirm the stated correct_index is actually correct and options are distinct.
- Clarity: no ambiguity, no leaked answer in the stem.

Overall checks (budget-aware):
- The total number of questions is fixed. If there are more weighted skills than questions, it is EXPECTED and CORRECT that only the highest-weight skills are covered.
- Only mark "missing_skills" if a skill with a clearly high weight (top of the weighted list) has ZERO questions.
- Balance: distribution of questions should roughly follow the TOP skills' weights, proportional to the question budget.

Return:
- ok: true if the set is acceptable, false only if there are real per-question issues or a top-weight skill is ignored.
- issues: list of short strings describing concrete problems (do NOT complain that low-weight skills have no coverage).
- questions_to_regenerate: list of 0-based indices that must be regenerated because of per-question problems.
- missing_skills: only skills in the TOP-N (where N = number of questions) that have zero coverage.

Be strict but fair. Prefer ok=true when the only "issue" is limited budget vs long skill list."""

QUESTION_VALIDATOR_USER_PROMPT = """Validate the following generated assessment.

NUMBER OF QUESTIONS IN THE SET: {{num_questions}}
(If there are more weighted skills than this number, coverage can and should focus on the top-weighted skills only.)

JOB DESCRIPTION:
---
{{grounding_text}}
---

WEIGHTED SKILLS (top-weighted first):
{{weighted_skills}}

GENERATED QUESTIONS (JSON):
{{questions_json}}
"""
