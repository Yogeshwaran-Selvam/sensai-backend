import json
from typing import Dict, Optional
from api.config import quiz_generation_configs_table_name
from api.utils.db import get_new_db_connection


def convert_quiz_generation_db_to_dict(row) -> Dict:
    return {
        "id": row[0],
        "course_title": row[1],
        "module_title": row[2],
        "purpose": row[3],
        "length": row[4],
        "difficulty": row[5],
        "question_type": row[6],
        "answer_type": row[7],
        "topic_weights": json.loads(row[8]) if row[8] else [],
        "course_id": row[9],
        "org_id": row[10],
        "status": row[11],
        "created_at": row[12],
    }


async def create_quiz_generation_config(
    course_title: str,
    module_title: str,
    purpose: str,
    length: int,
    difficulty: str,
    question_type: str,
    answer_type: str,
    topic_weights: list,
    course_id: int,
    org_id: int,
) -> Dict:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()

        await cursor.execute(
            f"""INSERT INTO {quiz_generation_configs_table_name}
                (course_title, module_title, purpose, length, difficulty,
                 question_type, answer_type, topic_weights, course_id, org_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                course_title,
                module_title,
                purpose,
                length,
                difficulty,
                question_type,
                answer_type,
                json.dumps([w.model_dump() for w in topic_weights]),
                course_id,
                org_id,
                "pending",
            ),
        )

        config_id = cursor.lastrowid
        await conn.commit()

        await cursor.execute(
            f"SELECT id, course_title, module_title, purpose, length, difficulty, question_type, answer_type, topic_weights, course_id, org_id, status, created_at FROM {quiz_generation_configs_table_name} WHERE id = ?",
            (config_id,),
        )
        row = await cursor.fetchone()
        return convert_quiz_generation_db_to_dict(row)


async def get_quiz_generation_config(config_id: int) -> Optional[Dict]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"SELECT * FROM {quiz_generation_configs_table_name} WHERE id = ?",
            (config_id,),
        )
        row = await cursor.fetchone()
        if row:
            return convert_quiz_generation_db_to_dict(row)
        return None
