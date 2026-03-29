"""Pydantic models for the ZIP comparison API."""

from pydantic import BaseModel
from typing import Optional


class DiffEntry(BaseModel):
    """Represents a single file/folder diff entry."""
    file_path: str
    status: str  # "added", "deleted", "modified", "unchanged", "renamed"
    diff_text: Optional[str] = None  # unified diff string
    old_size: Optional[int] = None
    new_size: Optional[int] = None
    is_binary: bool = False
    is_directory: bool = False
    additions: int = 0
    deletions: int = 0


class ComparisonSummary(BaseModel):
    """Summary statistics for a comparison."""
    total_files: int = 0
    added: int = 0
    deleted: int = 0
    modified: int = 0
    unchanged: int = 0


class ComparisonResult(BaseModel):
    """Full comparison result returned after upload."""
    id: str
    created_at: str
    original_filename: str
    modified_filename: str
    summary: ComparisonSummary
    entries: list[DiffEntry]


class ComparisonListItem(BaseModel):
    """Item in the comparison history list."""
    id: str
    created_at: str
    original_filename: str
    modified_filename: str
    summary: ComparisonSummary
