# --- START OF FILE sensai-api/sensai_backend/routes/org_routes.py ---
from fastapi import APIRouter, HTTPException, Body
import traceback
from typing import List, Dict, Annotated
from api.db.org import (
    create_organization_with_user,
    get_org_by_id as get_org_by_id_from_db,
    update_org as update_org_in_db,
    add_users_to_org_by_email as add_users_to_org_by_email_in_db,
    remove_members_from_org as remove_members_from_org_from_db,
    get_org_members as get_org_members_from_db,
    get_org_by_slug as get_org_by_slug_from_db,
    get_all_orgs as get_all_orgs_from_db,
)
from api.utils.db import get_new_db_connection
from api.models import (
    CreateOrganizationRequest,
    CreateOrganizationResponse,
    RemoveMembersFromOrgRequest,
    AddUsersToOrgRequest,
    UpdateOrgRequest,
    UpdateOrgOpenaiApiKeyRequest,
    JobDescriptionResponse,
)

router = APIRouter()


@router.post("/")
async def create_organization(
    request: CreateOrganizationRequest,
) -> CreateOrganizationResponse:
    try:
        org_id = await create_organization_with_user(
            request.name,
            request.slug,
            request.user_id,
        )

        return {"id": org_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{org_id}")
async def get_org_by_id(org_id: int) -> Dict:
    org_details = await get_org_by_id_from_db(org_id)

    if not org_details:
        raise HTTPException(status_code=404, detail="Organization not found")

    return org_details


@router.get("/slug/{slug}")
async def get_org_by_slug(slug: str) -> Dict:
    org_details = await get_org_by_slug_from_db(slug)

    if not org_details:
        raise HTTPException(status_code=404, detail="Organization not found")

    return org_details


@router.put("/{org_id}")
async def update_org(org_id: int, request: UpdateOrgRequest):
    await update_org_in_db(org_id, request.name)
    return {"success": True}


@router.post("/{org_id}/members")
async def add_users_to_org_by_email(org_id: int, request: AddUsersToOrgRequest):
    try:
        await add_users_to_org_by_email_in_db(org_id, request.emails)
        return {"success": True}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{org_id}/members")
async def remove_members_from_org(org_id: int, request: RemoveMembersFromOrgRequest):
    await remove_members_from_org_from_db(org_id, request.user_ids)
    return {"success": True}


@router.get("/{org_id}/members")
async def get_org_members(org_id: int) -> List[Dict]:
    return await get_org_members_from_db(org_id)


@router.get("/")
async def get_all_orgs() -> List[Dict]:
    return await get_all_orgs_from_db()


@router.get("/{org_id}/job-descriptions", response_model=JobDescriptionResponse)
async def get_job_descriptions(org_id: int):
    from api.db.course import get_top_courses_with_keywords
    from api.config import openai_plan_to_model_name
    from api.llm import run_llm_with_openai
    from api.prompts import compile_prompt
    from api.prompts.job_description import (
        JOB_DESCRIPTION_SYSTEM_PROMPT,
        JOB_DESCRIPTION_USER_PROMPT,
    )

    courses = await get_top_courses_with_keywords(org_id, limit=3)

    # Build course keywords text for the prompt
    course_keyword_parts = []
    for course in courses:
        if course["keywords"]:
            keywords_str = ", ".join(course["keywords"])
            course_keyword_parts.append(
                f"Course: {course['name']}\nKeywords: {keywords_str}"
            )

    if not course_keyword_parts:
        raise HTTPException(
            status_code=400,
            detail="No course keywords found. Add content to courses and let keywords be extracted first.",
        )

    course_keywords_text = "\n\n".join(course_keyword_parts)

    messages = compile_prompt(
        JOB_DESCRIPTION_SYSTEM_PROMPT,
        JOB_DESCRIPTION_USER_PROMPT,
        course_keywords=course_keywords_text,
    )

    model = openai_plan_to_model_name["text-mini"]

    result = await run_llm_with_openai(
        model=model,
        messages=messages,
        response_model=JobDescriptionResponse,
        max_output_tokens=4096,
    )

    return result
