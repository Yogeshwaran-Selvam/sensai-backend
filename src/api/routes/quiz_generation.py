import json
from fastapi import APIRouter, HTTPException
from api.models import CreateQuizGenerationRequest, QuizGenerationResponse, TopicWeight
from api.db.quiz_generation import create_quiz_generation_config, get_quiz_generation_config
from api.utils.logging import logger

router = APIRouter()


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
