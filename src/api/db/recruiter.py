"""DB helpers for the recruiter MCQ generation workflow."""

import json
from typing import Any, Dict, List, Optional

from api.config import recruiter_mcq_generations_table_name
from api.utils.db import get_new_db_connection


async def create_recruiter_generations_table(cursor):
    await cursor.execute(
        f"""CREATE TABLE IF NOT EXISTS {recruiter_mcq_generations_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                flow TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                jd_type TEXT,
                jd_text TEXT,
                resume_text TEXT,
                synthesized_jd TEXT,
                extracted_skills TEXT,
                weighted_skills TEXT,
                questions TEXT,
                validator_report TEXT,
                error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
    )


def _row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return None

    def _maybe_json(val):
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    return {
        "id": row[0],
        "org_id": row[1],
        "flow": row[2],
        "status": row[3],
        "jd_type": row[4],
        "jd_text": row[5],
        "resume_text": row[6],
        "synthesized_jd": _maybe_json(row[7]),
        "extracted_skills": _maybe_json(row[8]),
        "weighted_skills": _maybe_json(row[9]),
        "questions": _maybe_json(row[10]),
        "validator_report": _maybe_json(row[11]),
        "error": row[12],
        "created_at": row[13],
        "updated_at": row[14],
    }


_SELECT_COLS = (
    "id, org_id, flow, status, jd_type, jd_text, resume_text, "
    "synthesized_jd, extracted_skills, weighted_skills, questions, "
    "validator_report, error, created_at, updated_at"
)


async def create_recruiter_generation(
    org_id: int,
    flow: str,
    status: str = "pending",
    jd_text: Optional[str] = None,
    resume_text: Optional[str] = None,
) -> Dict[str, Any]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await create_recruiter_generations_table(cursor)
        await cursor.execute(
            f"""INSERT INTO {recruiter_mcq_generations_table_name}
                (org_id, flow, status, jd_text, resume_text)
                VALUES (?, ?, ?, ?, ?)""",
            (org_id, flow, status, jd_text, resume_text),
        )
        gen_id = cursor.lastrowid
        await conn.commit()
        await cursor.execute(
            f"SELECT {_SELECT_COLS} FROM {recruiter_mcq_generations_table_name} WHERE id = ?",
            (gen_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row)


async def update_recruiter_generation(gen_id: int, **fields) -> Dict[str, Any]:
    json_fields = {
        "synthesized_jd",
        "extracted_skills",
        "weighted_skills",
        "questions",
        "validator_report",
    }
    if not fields:
        return await get_recruiter_generation(gen_id)

    assignments = []
    values: List[Any] = []
    for key, value in fields.items():
        if value is None:
            assignments.append(f"{key} = ?")
            values.append(None)
        elif key in json_fields:
            assignments.append(f"{key} = ?")
            values.append(json.dumps(value))
        else:
            assignments.append(f"{key} = ?")
            values.append(value)

    assignments.append("updated_at = CURRENT_TIMESTAMP")
    values.append(gen_id)

    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"UPDATE {recruiter_mcq_generations_table_name} SET {', '.join(assignments)} WHERE id = ?",
            tuple(values),
        )
        await conn.commit()
        await cursor.execute(
            f"SELECT {_SELECT_COLS} FROM {recruiter_mcq_generations_table_name} WHERE id = ?",
            (gen_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row)


async def get_recruiter_generation(gen_id: int) -> Optional[Dict[str, Any]]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"SELECT {_SELECT_COLS} FROM {recruiter_mcq_generations_table_name} WHERE id = ?",
            (gen_id,),
        )
        row = await cursor.fetchone()
        return _row_to_dict(row)


async def list_recruiter_generations(org_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await create_recruiter_generations_table(cursor)
        await cursor.execute(
            f"SELECT {_SELECT_COLS} FROM {recruiter_mcq_generations_table_name} "
            f"WHERE org_id = ? ORDER BY id DESC LIMIT ?",
            (org_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]
