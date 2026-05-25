from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from .models import (
    BoardRecord,
    ChangelogItemRecord,
    ConfluencePageRecord,
    IssueRecord,
    JiraProjectVersionRecord,
    SprintRecord,
    SyncBatch,
)


@dataclass
class ConnectorConfig:
    base_url: str
    pat_token: str
    auth_mode: str = "pat_bearer"
    username: str | None = None
    timeout_seconds: int = 30
    ca_bundle_path: str | None = None


class JiraConnector(ABC):
    @abstractmethod
    def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
    ) -> tuple[list[IssueRecord], SyncBatch]:
        """Run JQL search and return normalized issue records."""

    @abstractmethod
    def incremental_issues(
        self,
        updated_since: datetime | None,
        start_at: int = 0,
        max_results: int = 100,
    ) -> tuple[list[IssueRecord], SyncBatch]:
        """Fetch issues updated since a cursor for scheduled sync."""

    @abstractmethod
    def get_boards(self) -> list[BoardRecord]:
        """List accessible agile boards."""

    @abstractmethod
    def get_project_versions(self, project_key: str) -> list[JiraProjectVersionRecord]:
        """List project versions/releases used by fixVersion planning."""

    @abstractmethod
    def get_sprints(self, board_id: int, state: str | None = None) -> list[SprintRecord]:
        """List sprints for a board."""

    @abstractmethod
    def get_board_issues(
        self,
        board_id: int,
        start_at: int = 0,
        max_results: int = 100,
        jql: str | None = None,
    ) -> tuple[list[IssueRecord], SyncBatch, int | None]:
        """Fetch paged issues for a specific board."""

    @abstractmethod
    def get_issue_changelog(self, issue_key: str) -> list[ChangelogItemRecord]:
        """Fetch changelog history for one issue."""


class ConfluenceConnector(ABC):
    @abstractmethod
    def get_page_by_id(self, page_id: str) -> ConfluencePageRecord:
        """Fetch a page by Confluence content id."""

    @abstractmethod
    def get_page_by_url(self, url: str) -> ConfluencePageRecord:
        """Resolve and fetch a page by URL."""

    @abstractmethod
    def list_pages_updated_since(
        self,
        updated_since: datetime | None,
        start: int = 0,
        limit: int = 50,
    ) -> tuple[list[ConfluencePageRecord], SyncBatch]:
        """Fetch updated pages for incremental sync."""
