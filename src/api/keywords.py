import asyncio
from api.utils.logging import logger


async def extract_and_save_keywords_for_task(task_id: int):
    """Background task: given a task_id, find its course/milestone and re-extract keywords for that milestone."""
    try:
        from api.db.task import get_task_metadata
        from api.db.course import (
            get_all_task_content_for_milestone,
            save_keywords_for_milestone,
        )
        from api.config import openai_plan_to_model_name
        from api.llm import run_llm_with_openai
        from api.prompts import compile_prompt
        from api.prompts.keyword_extraction import (
            KEYWORD_EXTRACTION_SYSTEM_PROMPT,
            KEYWORD_EXTRACTION_USER_PROMPT,
        )
        from api.models import ExtractKeywordsResponse

        metadata = await get_task_metadata(task_id)
        if not metadata:
            return

        course_id = metadata["course"]["id"]
        milestone_id = metadata["milestone"]["id"]

        module_content = await get_all_task_content_for_milestone(course_id, milestone_id)
        if not module_content.strip():
            return

        messages = compile_prompt(
            KEYWORD_EXTRACTION_SYSTEM_PROMPT,
            KEYWORD_EXTRACTION_USER_PROMPT,
            module_content=module_content,
        )

        model = openai_plan_to_model_name["text-mini"]

        result = await run_llm_with_openai(
            model=model,
            messages=messages,
            response_model=ExtractKeywordsResponse,
            max_output_tokens=4096,
        )

        await save_keywords_for_milestone(milestone_id, result.keywords)
        logger.info(
            f"Extracted {len(result.keywords)} keywords for milestone {milestone_id} (task {task_id})"
        )
    except Exception as e:
        logger.error(f"Failed to extract keywords for task {task_id}: {e}")


def trigger_keyword_extraction(task_id: int):
    """Fire-and-forget: schedule keyword extraction in the background without blocking the response."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(extract_and_save_keywords_for_task(task_id))
    except RuntimeError:
        pass
