"""DB helpers for published recruiter tests and candidate attempts."""

import json
import secrets
import string
from typing import Any, Dict, List, Optional

from api.config import (
    recruiter_test_attempts_table_name,
    recruiter_tests_table_name,
)
from api.utils.db import get_new_db_connection


TEST_COLS = (
    "id, generation_id, org_id, test_code, title, questions, status, created_at"
)

ATTEMPT_COLS = (
    "id, test_id, candidate_name, candidate_email, answers, score, max_score, "
    "status, started_at, submitted_at"
)


async def create_recruiter_tests_tables(cursor):
    await cursor.execute(
        f"""CREATE TABLE IF NOT EXISTS {recruiter_tests_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generation_id INTEGER,
                org_id INTEGER NOT NULL,
                test_code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                questions TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
    )
    await cursor.execute(
        f"""CREATE TABLE IF NOT EXISTS {recruiter_test_attempts_table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                candidate_name TEXT,
                candidate_email TEXT,
                answers TEXT,
                score REAL,
                max_score REAL,
                status TEXT NOT NULL DEFAULT 'in_progress',
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                submitted_at DATETIME,
                FOREIGN KEY (test_id) REFERENCES {recruiter_tests_table_name}(id) ON DELETE CASCADE
            )"""
    )


def _test_row_to_dict(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {
        "id": row[0],
        "generation_id": row[1],
        "org_id": row[2],
        "test_code": row[3],
        "title": row[4],
        "questions": json.loads(row[5]) if row[5] else [],
        "status": row[6],
        "created_at": row[7],
    }


def _attempt_row_to_dict(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {
        "id": row[0],
        "test_id": row[1],
        "candidate_name": row[2],
        "candidate_email": row[3],
        "answers": json.loads(row[4]) if row[4] else [],
        "score": row[5],
        "max_score": row[6],
        "status": row[7],
        "started_at": row[8],
        "submitted_at": row[9],
    }


def generate_test_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    # Avoid visually confusing characters
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create_recruiter_test(
    org_id: int,
    title: str,
    questions: List[Dict[str, Any]],
    generation_id: Optional[int] = None,
) -> Dict[str, Any]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await create_recruiter_tests_tables(cursor)

        for _ in range(8):
            code = generate_test_code()
            try:
                await cursor.execute(
                    f"""INSERT INTO {recruiter_tests_table_name}
                        (generation_id, org_id, test_code, title, questions)
                        VALUES (?, ?, ?, ?, ?)""",
                    (generation_id, org_id, code, title, json.dumps(questions)),
                )
                break
            except Exception:
                continue
        else:
            raise RuntimeError("Could not allocate a unique test code")

        test_id = cursor.lastrowid
        await conn.commit()
        await cursor.execute(
            f"SELECT {TEST_COLS} FROM {recruiter_tests_table_name} WHERE id = ?",
            (test_id,),
        )
        row = await cursor.fetchone()
        return _test_row_to_dict(row)


async def get_test_by_code(test_code: str) -> Optional[Dict[str, Any]]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await create_recruiter_tests_tables(cursor)
        await cursor.execute(
            f"SELECT {TEST_COLS} FROM {recruiter_tests_table_name} WHERE test_code = ?",
            (test_code.upper(),),
        )
        row = await cursor.fetchone()
        return _test_row_to_dict(row)


async def get_test_by_id(test_id: int) -> Optional[Dict[str, Any]]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"SELECT {TEST_COLS} FROM {recruiter_tests_table_name} WHERE id = ?",
            (test_id,),
        )
        row = await cursor.fetchone()
        return _test_row_to_dict(row)


async def list_tests_for_org(org_id: int) -> List[Dict[str, Any]]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await create_recruiter_tests_tables(cursor)
        await cursor.execute(
            f"SELECT {TEST_COLS} FROM {recruiter_tests_table_name} "
            f"WHERE org_id = ? AND status = 'active' ORDER BY id DESC",
            (org_id,),
        )
        rows = await cursor.fetchall()
        return [_test_row_to_dict(r) for r in rows]


async def create_attempt(
    test_id: int, candidate_name: str, candidate_email: str
) -> Dict[str, Any]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""INSERT INTO {recruiter_test_attempts_table_name}
                (test_id, candidate_name, candidate_email, status)
                VALUES (?, ?, ?, 'in_progress')""",
            (test_id, candidate_name, candidate_email),
        )
        attempt_id = cursor.lastrowid
        await conn.commit()
        await cursor.execute(
            f"SELECT {ATTEMPT_COLS} FROM {recruiter_test_attempts_table_name} WHERE id = ?",
            (attempt_id,),
        )
        row = await cursor.fetchone()
        return _attempt_row_to_dict(row)


async def submit_attempt(
    attempt_id: int,
    answers: List[Dict[str, Any]],
    score: float,
    max_score: float,
) -> Dict[str, Any]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""UPDATE {recruiter_test_attempts_table_name}
                SET answers = ?, score = ?, max_score = ?, status = 'submitted',
                    submitted_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (json.dumps(answers), score, max_score, attempt_id),
        )
        await conn.commit()
        await cursor.execute(
            f"SELECT {ATTEMPT_COLS} FROM {recruiter_test_attempts_table_name} WHERE id = ?",
            (attempt_id,),
        )
        row = await cursor.fetchone()
        return _attempt_row_to_dict(row)


async def get_attempt(attempt_id: int) -> Optional[Dict[str, Any]]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"SELECT {ATTEMPT_COLS} FROM {recruiter_test_attempts_table_name} WHERE id = ?",
            (attempt_id,),
        )
        row = await cursor.fetchone()
        return _attempt_row_to_dict(row)


async def list_attempts_for_test(test_id: int) -> List[Dict[str, Any]]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"SELECT {ATTEMPT_COLS} FROM {recruiter_test_attempts_table_name} "
            f"WHERE test_id = ? ORDER BY id DESC",
            (test_id,),
        )
        rows = await cursor.fetchall()
        return [_attempt_row_to_dict(r) for r in rows]


async def update_attempt_answers(
    attempt_id: int, answers: List[Dict[str, Any]]
) -> Dict[str, Any]:
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await cursor.execute(
            f"""UPDATE {recruiter_test_attempts_table_name}
                SET answers = ?
                WHERE id = ?""",
            (json.dumps(answers), attempt_id),
        )
        await conn.commit()
        await cursor.execute(
            f"SELECT {ATTEMPT_COLS} FROM {recruiter_test_attempts_table_name} WHERE id = ?",
            (attempt_id,),
        )
        row = await cursor.fetchone()
        return _attempt_row_to_dict(row)


async def get_attempt_counts_for_org(org_id: int) -> Dict[int, Dict[str, Any]]:
    """Return {test_id: {total, submitted, in_progress, avg_score, max_score}} for all tests in an org."""
    async with get_new_db_connection() as conn:
        cursor = await conn.cursor()
        await create_recruiter_tests_tables(cursor)
        await cursor.execute(
            f"""SELECT a.test_id,
                       COUNT(*) as total,
                       SUM(CASE WHEN a.status = 'submitted' THEN 1 ELSE 0 END) as submitted,
                       SUM(CASE WHEN a.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                       AVG(CASE WHEN a.status = 'submitted' THEN a.score ELSE NULL END) as avg_score,
                       MAX(CASE WHEN a.status = 'submitted' THEN a.max_score ELSE NULL END) as max_score
                FROM {recruiter_test_attempts_table_name} a
                JOIN {recruiter_tests_table_name} t ON a.test_id = t.id
                WHERE t.org_id = ?
                GROUP BY a.test_id""",
            (org_id,),
        )
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            result[row[0]] = {
                "total": row[1],
                "submitted": row[2],
                "in_progress": row[3],
                "avg_score": round(row[4], 1) if row[4] is not None else None,
                "max_score": row[5],
            }
        return result
