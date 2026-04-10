from enum import Enum
from pydantic import BaseModel
from typing import List, Tuple, Optional, Dict, Literal, Any
from datetime import datetime


class UserLoginData(BaseModel):
    email: str
    given_name: str
    family_name: str | None = None
    id_token: str  # Google authentication token


class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str
    user_id: int


class CreateOrganizationResponse(BaseModel):
    id: int


class RemoveMembersFromOrgRequest(BaseModel):
    user_ids: List[int]


class AddUsersToOrgRequest(BaseModel):
    emails: List[str]


class UpdateOrgRequest(BaseModel):
    name: str


class UpdateOrgOpenaiApiKeyRequest(BaseModel):
    encrypted_openai_api_key: str
    is_free_trial: bool


class AddMilestoneRequest(BaseModel):
    name: str
    color: str
    org_id: int


class UpdateMilestoneRequest(BaseModel):
    name: str


class CreateTagRequest(BaseModel):
    name: str
    org_id: int


class CreateBulkTagsRequest(BaseModel):
    tag_names: List[str]
    org_id: int


class CreateBadgeRequest(BaseModel):
    user_id: int
    value: str
    badge_type: str
    image_path: str
    bg_color: str
    cohort_id: int


class UpdateBadgeRequest(BaseModel):
    value: str
    badge_type: str
    image_path: str
    bg_color: str


class CreateCohortRequest(BaseModel):
    name: str
    org_id: int


class CreateCohortResponse(BaseModel):
    id: int


class AddMembersToCohortRequest(BaseModel):
    org_slug: Optional[str] = None
    org_id: Optional[int] = None
    emails: List[str]
    roles: List[str]


class RemoveMembersFromCohortRequest(BaseModel):
    member_ids: List[int]


class UpdateCohortRequest(BaseModel):
    name: str


class UpdateCohortGroupRequest(BaseModel):
    name: str


class CreateCohortGroupRequest(BaseModel):
    name: str
    member_ids: List[int]


class AddMembersToCohortGroupRequest(BaseModel):
    member_ids: List[int]


class RemoveMembersFromCohortGroupRequest(BaseModel):
    member_ids: List[int]


# Batch models
class CreateBatchRequest(BaseModel):
    name: str
    cohort_id: int
    user_ids: Optional[List[int]] = []


class CreateBatchResponse(BaseModel):
    id: int


class AddMembersToBatchRequest(BaseModel):
    user_ids: List[int]


class RemoveMembersFromBatchRequest(BaseModel):
    member_ids: List[int]


class UpdateBatchRequest(BaseModel):
    name: str
    members_added: Optional[List[int]] = []
    members_removed: Optional[List[int]] = []


class RemoveCoursesFromCohortRequest(BaseModel):
    course_ids: List[int]


class DripConfig(BaseModel):
    is_drip_enabled: Optional[bool] = False
    frequency_value: Optional[int] = None
    frequency_unit: Optional[str] = None
    publish_at: Optional[datetime] = None


class AddCoursesToCohortRequest(BaseModel):
    course_ids: List[int]
    drip_config: Optional[DripConfig] = DripConfig()


class CreateCourseRequest(BaseModel):
    name: str
    org_id: int


class CreateCourseResponse(BaseModel):
    id: int


class Course(BaseModel):
    id: int
    name: str


class CourseCohort(Course):
    drip_config: DripConfig


class CohortCourse(Course):
    drip_config: DripConfig


class Milestone(BaseModel):
    id: int
    name: str | None
    color: Optional[str] = None
    ordering: Optional[int] = None
    unlock_at: Optional[datetime] = None


class TaskType(Enum):
    QUIZ = "quiz"
    LEARNING_MATERIAL = "learning_material"
    ASSIGNMENT = "assignment"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, TaskType):
            return self.value == other.value
        return False


class TaskStatus(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, TaskStatus):
            return self.value == other.value

        return False


class Task(BaseModel):
    id: int
    title: str
    type: TaskType
    status: TaskStatus
    scheduled_publish_at: datetime | None


class Block(BaseModel):
    id: Optional[str] = None
    type: str
    props: Optional[Dict] = {}
    content: Optional[List] = []
    children: Optional[List] = []
    position: Optional[int] = (
        None  # not present when sent from frontend at the time of publishing
    )


class LearningMaterialTask(Task):
    blocks: List[Block]


class TaskInputType(Enum):
    CODE = "code"
    TEXT = "text"
    AUDIO = "audio"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, TaskInputType):
            return self.value == other.value

        return False


class TaskAIResponseType(Enum):
    CHAT = "chat"
    EXAM = "exam"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, TaskAIResponseType):
            return self.value == other.value

        return False


class QuestionType(Enum):
    OPEN_ENDED = "subjective"
    OBJECTIVE = "objective"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, QuestionType):
            return self.value == other.value

        return False


class ScorecardCriterion(BaseModel):
    name: str
    description: str
    min_score: float
    max_score: float
    pass_score: float


class ScorecardStatus(Enum):
    PUBLISHED = "published"
    DRAFT = "draft"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, ScorecardStatus):
            return self.value == other.value

        return False


class BaseScorecard(BaseModel):
    title: str
    criteria: List[ScorecardCriterion]


class CreateScorecardRequest(BaseScorecard):
    org_id: int


class NewScorecard(BaseScorecard):
    id: str | int


class Scorecard(BaseScorecard):
    id: int
    status: ScorecardStatus


class DraftQuestion(BaseModel):
    blocks: List[Block]
    answer: List[Block] | None
    type: QuestionType
    input_type: TaskInputType
    response_type: TaskAIResponseType
    context: Dict | None
    coding_languages: List[str] | None
    scorecard_id: Optional[int] = None
    title: str
    settings: Optional[Any] = None


class PublishedQuestion(DraftQuestion):
    id: int
    scorecard_id: Optional[int] = None
    max_attempts: Optional[int] = None
    is_feedback_shown: Optional[bool] = None


class QuizTask(Task):
    questions: List[PublishedQuestion]


class AssignmentEvaluationCriteria(BaseModel):
    scorecard_id: Optional[int] = None
    min_score: float
    max_score: float
    pass_score: float


class Assignment(BaseModel):
    blocks: List[Block]
    context: Optional[Dict] = None
    evaluation_criteria: AssignmentEvaluationCriteria | None = None
    input_type: TaskInputType | None = None
    response_type: TaskAIResponseType | None = None
    max_attempts: Optional[int] = None
    settings: Optional[Any] = None


class AssignmentTask(Task):
    assignment: Assignment


class AssignmentRequest(AssignmentTask):
    id: Optional[int] = None
    type: Optional[TaskType] = None
    status: Optional[str] = None


class GenerateCourseJobStatus(str, Enum):
    STARTED = "started"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, GenerateCourseJobStatus):
            return self.value == other.value
        return self == other


class GenerateTaskJobStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, GenerateTaskJobStatus):
            return self.value == other.value

        return False


class MilestoneTask(Task):
    ordering: int
    num_questions: int | None
    is_generating: Optional[bool] = False


class MilestoneTaskWithDetails(MilestoneTask):
    blocks: Optional[List[Block]] = None
    questions: Optional[List[PublishedQuestion]] = None


class MilestoneWithTasks(Milestone):
    tasks: List[MilestoneTask]


class MilestoneWithTaskDetails(Milestone):
    tasks: List[MilestoneTaskWithDetails]


class CourseWithMilestonesAndTasks(Course):
    milestones: List[MilestoneWithTasks]
    course_generation_status: Optional[GenerateCourseJobStatus] = None


class CourseWithMilestonesAndTaskDetails(CourseWithMilestonesAndTasks):
    milestones: List[MilestoneWithTaskDetails]
    course_generation_status: Optional[GenerateCourseJobStatus] = None


class UserCourseRole(str, Enum):
    ADMIN = "admin"
    LEARNER = "learner"
    MENTOR = "mentor"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, UserCourseRole):
            return self.value == other.value

        return False


class Organization(BaseModel):
    id: int
    name: str
    slug: str


class UserCourse(Course):
    role: UserCourseRole
    org: Organization
    cohort_id: Optional[int] = None


class AddCourseToCohortsRequest(BaseModel):
    cohort_ids: List[int]
    drip_config: Optional[DripConfig] = DripConfig()


class RemoveCourseFromCohortsRequest(BaseModel):
    cohort_ids: List[int]


class UpdateCourseNameRequest(BaseModel):
    name: str


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatResponseType(str, Enum):
    TEXT = "text"
    CODE = "code"
    AUDIO = "audio"
    FILE = "file"


class ChatMessage(BaseModel):
    id: int
    created_at: str
    user_id: int
    question_id: Optional[int] = None
    task_id: Optional[int] = None
    role: ChatRole | None
    content: Optional[str] | None
    response_type: Optional[ChatResponseType] | None


class PublicAPIChatMessage(ChatMessage):
    task_id: int
    user_email: str
    course_id: int
    created_at: datetime


class Tag(BaseModel):
    id: int
    name: str


class User(BaseModel):
    id: int
    email: str
    first_name: str | None
    middle_name: str | None
    last_name: str | None


class UserStreak(BaseModel):
    user: User
    count: int


Streaks = List[UserStreak]


class LeaderboardViewType(Enum):
    ALL_TIME = "All time"
    WEEKLY = "This week"
    MONTHLY = "This month"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, LeaderboardViewType):
            return self.value == other.value
        raise NotImplementedError


class CreateDraftTaskRequest(BaseModel):
    course_id: int
    milestone_id: int
    type: TaskType
    title: str


class CreateDraftTaskResponse(BaseModel):
    id: int


class PublishLearningMaterialTaskRequest(BaseModel):
    title: str
    blocks: List[dict]
    scheduled_publish_at: datetime | None


class UpdateLearningMaterialTaskRequest(PublishLearningMaterialTaskRequest):
    status: TaskStatus


class CreateQuestionRequest(DraftQuestion):
    id: Optional[int] = None
    generation_model: str | None
    max_attempts: int | None
    is_feedback_shown: bool | None
    context: Dict | None


class UpdateDraftQuizRequest(BaseModel):
    title: str
    questions: List[CreateQuestionRequest]
    scheduled_publish_at: datetime | None
    status: TaskStatus


class UpdateQuestionRequest(BaseModel):
    id: int
    blocks: List[dict]
    coding_languages: List[str] | None
    answer: List[Block] | None
    scorecard_id: Optional[int] = None
    input_type: TaskInputType | None
    context: Dict | None
    response_type: TaskAIResponseType | None
    type: QuestionType | None
    title: str
    settings: Optional[Any] = None


class UpdatePublishedQuizRequest(BaseModel):
    title: str
    questions: List[UpdateQuestionRequest]
    scheduled_publish_at: datetime | None


class DuplicateTaskRequest(BaseModel):
    task_id: int
    course_id: int
    milestone_id: int


class DuplicateTaskResponse(BaseModel):
    task: LearningMaterialTask | QuizTask | AssignmentTask
    ordering: int


class StoreMessageRequest(BaseModel):
    role: str
    content: str | None
    response_type: ChatResponseType | None = None
    created_at: datetime


class StoreMessagesRequest(BaseModel):
    messages: List[StoreMessageRequest]
    user_id: int
    question_id: Optional[int] = None
    task_id: Optional[int] = None
    is_complete: bool


class GetUserChatHistoryRequest(BaseModel):
    task_ids: List[int]


class TaskTagsRequest(BaseModel):
    tag_ids: List[int]


class AddScoringCriteriaToTasksRequest(BaseModel):
    task_ids: List[int]
    scoring_criteria: List[Dict]


class AddTasksToCoursesRequest(BaseModel):
    course_tasks: List[Tuple[int, int, int | None]]


class RemoveTasksFromCoursesRequest(BaseModel):
    course_tasks: List[Tuple[int, int]]


class UpdateTaskOrdersRequest(BaseModel):
    task_orders: List[Tuple[int, int]]


class AddMilestoneToCourseRequest(BaseModel):
    name: str
    color: str


class AddMilestoneToCourseResponse(BaseModel):
    id: int


class UpdateMilestoneOrdersRequest(BaseModel):
    milestone_orders: List[Tuple[int, int]]


class UpdateTaskTestsRequest(BaseModel):
    tests: List[dict]


class TaskCourse(Course):
    milestone: Milestone | None


class TaskCourseResponse(BaseModel):
    task_id: int
    courses: List[TaskCourse]


class AddCVReviewUsageRequest(BaseModel):
    user_id: int
    role: str
    ai_review: str


class Batch(BaseModel):
    id: int
    name: str


class UserCohort(BaseModel):
    id: int
    name: str
    role: Literal[UserCourseRole.LEARNER, UserCourseRole.MENTOR]
    joined_at: Optional[datetime] = None
    batches: Optional[List[Batch]] = []


class AIChatRequest(BaseModel):
    user_response: str
    task_type: TaskType
    question: Optional[DraftQuestion] = None
    chat_history: Optional[List[Dict]] = None
    question_id: Optional[int] = None
    user_id: int
    user_email: str
    task_id: int
    response_type: Optional[ChatResponseType] = None


class MarkTaskCompletedRequest(BaseModel):
    user_id: int


class GetUserStreakResponse(BaseModel):
    streak_count: int
    active_days: List[str]


class PresignedUrlRequest(BaseModel):
    content_type: str = "audio/wav"


class PresignedUrlResponse(BaseModel):
    presigned_url: str
    file_key: str
    file_uuid: str


class S3FetchPresignedUrlResponse(BaseModel):
    url: str


class SwapMilestoneOrderingRequest(BaseModel):
    milestone_1_id: int
    milestone_2_id: int


class SwapTaskOrderingRequest(BaseModel):
    task_1_id: int
    task_2_id: int


class GenerateCourseStructureRequest(BaseModel):
    course_description: str
    intended_audience: str
    instructions: Optional[str] = None
    reference_material_s3_key: str


class LanguageCodeDraft(BaseModel):
    language: str
    value: str


class SaveCodeDraftRequest(BaseModel):
    user_id: int
    question_id: int
    code: List[LanguageCodeDraft]


class CodeDraft(BaseModel):
    id: int
    code: List[LanguageCodeDraft]


class DuplicateCourseRequest(BaseModel):
    org_id: int


class Integration(BaseModel):
    id: int
    user_id: int
    integration_type: str
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None

class CreateIntegrationRequest(BaseModel):
    user_id: int
    integration_type: str
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None

class UpdateIntegrationRequest(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None



# ============================================================
# Bloom's Taxonomy Assessment Intelligence Engine Models
# ============================================================

class BloomsLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        elif isinstance(other, BloomsLevel):
            return self.value == other.value
        return False


class BloomsDistribution(BaseModel):
    remember: int = 20
    understand: int = 20
    apply: int = 20
    analyze: int = 20
    evaluate: int = 10
    create: int = 10


class BloomsGenerateRequest(BaseModel):
    course_id: int
    milestone_id: int
    task_id: Optional[int] = None  # specific learning material task (optional)
    num_questions: int = 10
    difficulty: str = "medium"  # easy, medium, hard
    question_types: List[str] = ["objective"]  # objective, subjective
    bloom_distribution: BloomsDistribution = BloomsDistribution()
    learning_material_content: Optional[str] = None  # pre-fetched content to skip DB lookup


class GeneratedBloomsQuestion(BaseModel):
    question_text: str
    blooms_level: str
    options: Optional[List[str]] = None
    correct_answer: str
    explanation: str
    source_reference: str
    difficulty: str
    question_type: str  # objective or subjective


class BloomsAssessmentOutput(BaseModel):
    questions: List[GeneratedBloomsQuestion]


class BloomsVerifyRequest(BaseModel):
    questions: List[GeneratedBloomsQuestion]
    learning_material_content: str


# --- Scenario Mode ---


class ScenarioGenerateRequest(BaseModel):
    course_id: int
    milestone_id: int
    task_id: Optional[int] = None
    num_questions: int = 8
    difficulty: str = "medium"  # easy, medium, hard
    question_types: List[str] = ["objective"]  # objective, subjective
    learning_material_content: Optional[str] = None  # pre-fetched content to skip DB lookup


class GeneratedScenarioQuestion(BaseModel):
    question_text: str
    options: Optional[List[str]] = None
    correct_answer: str
    explanation: str
    concept_tested: str  # which concept from the learning material is being tested
    difficulty: str
    question_type: str  # objective or subjective


class ScenarioAssessmentOutput(BaseModel):
    scenario_narrative: str  # the scenario story
    scenario_title: str  # short title for the scenario
    questions: List[GeneratedScenarioQuestion]


class ScenarioVerifyRequest(BaseModel):
    questions: List[GeneratedScenarioQuestion]
    scenario_narrative: str
    learning_material_content: str


# --- Believer Mode (Adaptive Diagnostic Practice) ---


class BelieverStartRequest(BaseModel):
    course_id: int
    milestone_id: int


class BelieverTopicInfo(BaseModel):
    keyword: str
    status: str = "pending"  # pending, strong, moderate, basic, weak
    current_difficulty: str = "hard"  # hard, medium, easy
    attempts: int = 0
    correct: int = 0


class BelieverStartResponse(BaseModel):
    topics: List[BelieverTopicInfo]
    first_question: dict
    current_topic_index: int
    learning_content: str


class BelieverNextRequest(BaseModel):
    course_id: int
    milestone_id: int
    selected_option: str  # the learner's answer
    correct_answer: str  # the actual correct answer
    current_topic: str
    current_difficulty: str  # difficulty of the question they just answered
    was_correct: bool
    remaining_topics: List[str]  # topics not yet attempted
    questions_asked: int  # total questions asked so far


class BelieverNextResponse(BaseModel):
    is_session_complete: bool
    next_question: Optional[dict] = None
    next_topic: Optional[str] = None
    next_difficulty: Optional[str] = None
    topic_result: Optional[dict] = None  # result of topic that just concluded
    feedback: str  # feedback for the answer they just gave


class BelieverReportRequest(BaseModel):
    module_name: str
    topic_results: List[dict]
    correct_count: int
    total_count: int


class BelieverReportResponse(BaseModel):
    overall_assessment: str
    study_recommendations: List[str]
    topic_mastery: List[dict]
    overall_score: float


class ExtractKeywordsResponse(BaseModel):
    keywords: List[str]


class MilestoneKeywordsResponse(BaseModel):
    milestone_id: int
    keywords: List[str]


class JobDescription(BaseModel):
    title: str
    description: str
    responsibilities: List[str]
    skills: List[str]


class JobDescriptionResponse(BaseModel):
    jobs: List[JobDescription]

# --- Quiz Generation ---


class QuizGenerationPurpose(str, Enum):
    practice = "practice"
    exam = "exam"


class QuizGenerationDifficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class QuizGenQuestionType(str, Enum):
    objective = "objective"
    subjective = "subjective"


class QuizGenAnswerType(str, Enum):
    mcq = "mcq"
    fill_in_the_blanks = "fill_in_the_blanks"
    short_answer = "short_answer"
    long_answer = "long_answer"
    code = "code"


class TopicWeight(BaseModel):
    keyword: str
    weight: float  # 0-100


class CreateQuizGenerationRequest(BaseModel):
    course_title: str
    module_title: str
    purpose: QuizGenerationPurpose
    length: int  # 10, 15, 20
    difficulty: QuizGenerationDifficulty
    question_type: QuizGenQuestionType
    answer_type: QuizGenAnswerType
    topic_weights: List[TopicWeight]
    course_id: int
    org_id: int


class QuizGenerationResponse(BaseModel):
    id: int
    course_title: str
    module_title: str
    purpose: str
    length: int
    difficulty: str
    question_type: str
    answer_type: str
    topic_weights: List[TopicWeight]
    course_id: int
    org_id: int
    status: str
    created_at: str


class QuizGenBloomsDistribution(BaseModel):
    remember: int = 20
    understand: int = 20
    apply: int = 20
    analyze: int = 20
    evaluate: int = 10
    create: int = 10


class GenerateQuestionsRequest(BaseModel):
    course_title: str
    module_title: str
    purpose: QuizGenerationPurpose
    length: int
    difficulty: QuizGenerationDifficulty
    question_type: QuizGenQuestionType
    answer_type: QuizGenAnswerType
    topic_weights: List[TopicWeight]
    bloom_distribution: Optional[QuizGenBloomsDistribution] = None


class RegenerateQuestionRequest(BaseModel):
    topic: str
    blooms_level: str
    course_title: str
    module_title: str
    difficulty: QuizGenerationDifficulty
    question_type: QuizGenQuestionType
    answer_type: QuizGenAnswerType
