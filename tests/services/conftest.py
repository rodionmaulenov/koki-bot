"""Fixtures for service unit tests — all dependencies mocked."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.add_service import AddService
from services.video_service import VideoService


# =============================================================================
# MOCK DEPENDENCIES
# =============================================================================


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Mock Supabase client. Configure RPC chains per test."""
    return MagicMock()


@pytest.fixture
def mock_course_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_intake_log_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    return AsyncMock()


# =============================================================================
# SERVICE INSTANCES (with mocked deps)
# =============================================================================


@pytest.fixture
def service(mock_course_repo, mock_intake_log_repo) -> VideoService:
    return VideoService(mock_course_repo, mock_intake_log_repo)


@pytest.fixture
def add_service(
    mock_supabase, mock_user_repo, mock_course_repo,
) -> AddService:
    return AddService(mock_supabase, mock_user_repo, mock_course_repo)


# =============================================================================
# TIME FREEZING
# =============================================================================


@pytest.fixture
def frozen_now():
    """Patch get_tashkent_now() in video_service module.

    Usage:
        def test_something(self, service, frozen_now):
            frozen_now.return_value = datetime(2026, 6, 15, 14, 0, tzinfo=TASHKENT_TZ)
    """
    with patch("services.video_service.get_tashkent_now") as mock:
        yield mock