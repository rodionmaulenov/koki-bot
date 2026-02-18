from collections.abc import AsyncIterator

from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dishka import Provider, Scope, provide
from redis.asyncio import Redis
from supabase import AsyncClient, acreate_client

from config import Settings
from repositories.commands_messages_repository import CommandsMessagesRepository
from repositories.course_repository import CourseRepository
from repositories.intake_log_repository import IntakeLogRepository
from repositories.manager_repository import ManagerRepository
from repositories.owner_repository import OwnerRepository
from repositories.user_repository import UserRepository
from services.add_service import AddService
from services.gemini_service import GeminiService
from services.ocr_service import OCRService
from services.video_service import VideoService
from topic_access.service import CommandsMessagesService
from topic_access.tracked_bot import TrackedBot


class AppProvider(Provider):
    scope = Scope.APP

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @provide
    def get_settings(self) -> Settings:
        return self._settings

    @provide
    async def get_supabase(self) -> AsyncIterator[AsyncClient]:
        client = await acreate_client(
            self._settings.supabase_url,
            self._settings.supabase_key,
        )
        yield client

    @provide
    async def get_redis(self) -> AsyncIterator[Redis]:
        redis = Redis.from_url(self._settings.redis_url, decode_responses=True)
        yield redis
        await redis.aclose()

    @provide
    def get_manager_repository(
        self,
        supabase: AsyncClient,
    ) -> ManagerRepository:
        return ManagerRepository(supabase)

    @provide
    def get_owner_repository(
        self,
        supabase: AsyncClient,
    ) -> OwnerRepository:
        return OwnerRepository(supabase)

    @provide
    def get_commands_messages_repository(
        self,
        supabase: AsyncClient,
    ) -> CommandsMessagesRepository:
        return CommandsMessagesRepository(supabase, self._settings.bot_type)

    @provide
    async def get_tracked_bot(
        self,
        repository: CommandsMessagesRepository,
    ) -> AsyncIterator[TrackedBot]:
        bot = TrackedBot(
            token=self._settings.bot_token,
            repository=repository,
            thread_id=self._settings.commands_thread_id,
            chat_id=self._settings.commands_group_id,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        yield bot
        await bot.session.close()

    @provide
    def get_user_repository(
        self,
        supabase: AsyncClient,
    ) -> UserRepository:
        return UserRepository(supabase)

    @provide
    def get_course_repository(
        self,
        supabase: AsyncClient,
    ) -> CourseRepository:
        return CourseRepository(supabase)

    @provide
    def get_commands_messages_service(
        self,
        bot: TrackedBot,
        repository: CommandsMessagesRepository,
    ) -> CommandsMessagesService:
        return CommandsMessagesService(
            bot=bot,
            repository=repository,
            chat_id=self._settings.commands_group_id,
        )

    @provide
    def get_add_service(
        self,
        supabase: AsyncClient,
        user_repository: UserRepository,
        course_repository: CourseRepository,
    ) -> AddService:
        return AddService(
            supabase=supabase,
            user_repository=user_repository,
            course_repository=course_repository,
        )

    @provide
    def get_intake_log_repository(
        self,
        supabase: AsyncClient,
    ) -> IntakeLogRepository:
        return IntakeLogRepository(supabase)

    @provide
    def get_video_service(
        self,
        course_repository: CourseRepository,
        intake_log_repository: IntakeLogRepository,
    ) -> VideoService:
        return VideoService(
            course_repository=course_repository,
            intake_log_repository=intake_log_repository,
        )

    @provide
    def get_gemini_service(self) -> GeminiService:
        return GeminiService(api_key=self._settings.gemini_api_key)

    @provide
    def get_ocr_service(
        self,
        gemini: GeminiService,
        bot: TrackedBot,
    ) -> OCRService:
        return OCRService(gemini=gemini, bot=bot)

