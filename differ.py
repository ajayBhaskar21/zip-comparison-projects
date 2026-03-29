"""Core ZIP comparison and diff logic."""

import difflib
import os
import tempfile
import zipfile
import shutil
from pathlib import Path


# Binary file detection: common binary extensions
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flv",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".o", ".obj",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pyc", ".pyo", ".class", ".jar",
    ".db", ".sqlite", ".sqlite3",
    ".DS_Store",
}


def is_binary_file(filepath: str) -> bool:
    """Check if a file is binary by extension and content sampling."""
    ext = Path(filepath).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return True
    # Sample the file for null bytes
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return True
    except (IOError, OSError):
        return True
    return False


def get_file_content(filepath: str) -> list[str] | None:
    """Read file content as a list of lines. Returns None if binary."""
    if is_binary_file(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except (IOError, OSError):
        return None


def compute_diff(old_path: str | None, new_path: str | None,
                 relative_path: str) -> dict:
    """Compute the diff between two files.
    
    Returns a dict with: diff_text, additions, deletions, is_binary
    """
    old_is_binary = old_path and is_binary_file(old_path)
    new_is_binary = new_path and is_binary_file(new_path)

    if old_is_binary or new_is_binary:
        return {
            "diff_text": "Binary file changed",
            "additions": 0,
            "deletions": 0,
            "is_binary": True,
        }

    old_lines = get_file_content(old_path) if old_path else []
    new_lines = get_file_content(new_path) if new_path else []

    if old_lines is None:
        old_lines = []
    if new_lines is None:
        new_lines = []

    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{relative_path}",
        tofile=f"b/{relative_path}",
        lineterm=""
    ))

    # Strip trailing newlines from each diff line for clean output
    diff_lines = [line.rstrip("\n").rstrip("\r") for line in diff_lines]

    additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

    return {
        "diff_text": "\n".join(diff_lines),
        "additions": additions,
        "deletions": deletions,
        "is_binary": False,
    }


def compare_zips(zip1_path: str, zip2_path: str) -> tuple[dict, list[dict]]:
    """Compare two ZIP files and return (summary, entries).
    
    zip1_path: path to the "original" zip
    zip2_path: path to the "modified" zip
    
    Returns:
        summary: dict with total_files, added, deleted, modified, unchanged
        entries: list of diff entry dicts
    """
    temp_dir = tempfile.mkdtemp()
    dir1 = os.path.join(temp_dir, "original")
    dir2 = os.path.join(temp_dir, "modified")

    try:
        # Extract both ZIPs
        with zipfile.ZipFile(zip1_path, "r") as zf:
            zf.extractall(dir1)
        with zipfile.ZipFile(zip2_path, "r") as zf:
            zf.extractall(dir2)

        # Gather all relative paths (files only)
        old_files = set()
        for root, dirs, files in os.walk(dir1):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), dir1).replace("\\", "/")
                old_files.add(rel)

        new_files = set()
        for root, dirs, files in os.walk(dir2):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), dir2).replace("\\", "/")
                new_files.add(rel)

        all_files = sorted(old_files | new_files)

        # Also gather directories
        old_dirs = set()
        for root, dirs, files in os.walk(dir1):
            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d), dir1).replace("\\", "/")
                old_dirs.add(rel)

        new_dirs = set()
        for root, dirs, files in os.walk(dir2):
            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d), dir2).replace("\\", "/")
                new_dirs.add(rel)

        entries = []
        summary = {"total_files": 0, "added": 0, "deleted": 0, "modified": 0, "unchanged": 0}

        # Process directories
        all_dirs = sorted(old_dirs | new_dirs)
        for d in all_dirs:
            if d in old_dirs and d in new_dirs:
                status = "unchanged"
            elif d in new_dirs:
                status = "added"
            else:
                status = "deleted"

            entries.append({
                "file_path": d,
                "status": status,
                "diff_text": None,
                "old_size": None,
                "new_size": None,
                "is_binary": False,
                "is_directory": True,
                "additions": 0,
                "deletions": 0,
            })

        # Process files
        for f in all_files:
            old_path = os.path.join(dir1, f) if f in old_files else None
            new_path = os.path.join(dir2, f) if f in new_files else None

            old_size = os.path.getsize(old_path) if old_path and os.path.exists(old_path) else None
            new_size = os.path.getsize(new_path) if new_path and os.path.exists(new_path) else None

            if f in old_files and f in new_files:
                # Exists in both — check if modified
                diff_result = compute_diff(old_path, new_path, f)
                if diff_result["additions"] == 0 and diff_result["deletions"] == 0 and not diff_result["is_binary"]:
                    status = "unchanged"
                    diff_text = None
                    summary["unchanged"] += 1
                else:
                    # Could be binary that didn't change, or text that changed
                    if diff_result["is_binary"]:
                        # Check if binary content actually changed
                        with open(old_path, "rb") as a, open(new_path, "rb") as b:
                            if a.read() == b.read():
                                status = "unchanged"
                                diff_text = None
                                summary["unchanged"] += 1
                            else:
                                status = "modified"
                                diff_text = diff_result["diff_text"]
                                summary["modified"] += 1
                    else:
                        status = "modified"
                        diff_text = diff_result["diff_text"]
                        summary["modified"] += 1

                entries.append({
                    "file_path": f,
                    "status": status,
                    "diff_text": diff_text,
                    "old_size": old_size,
                    "new_size": new_size,
                    "is_binary": diff_result["is_binary"],
                    "is_directory": False,
                    "additions": diff_result["additions"] if status == "modified" else 0,
                    "deletions": diff_result["deletions"] if status == "modified" else 0,
                })
            elif f in new_files:
                # Added
                diff_result = compute_diff(None, new_path, f)
                summary["added"] += 1
                entries.append({
                    "file_path": f,
                    "status": "added",
                    "diff_text": diff_result["diff_text"],
                    "old_size": None,
                    "new_size": new_size,
                    "is_binary": diff_result["is_binary"],
                    "is_directory": False,
                    "additions": diff_result["additions"],
                    "deletions": 0,
                })
            else:
                # Deleted
                diff_result = compute_diff(old_path, None, f)
                summary["deleted"] += 1
                entries.append({
                    "file_path": f,
                    "status": "deleted",
                    "diff_text": diff_result["diff_text"],
                    "old_size": old_size,
                    "new_size": None,
                    "is_binary": diff_result["is_binary"],
                    "is_directory": False,
                    "additions": 0,
                    "deletions": diff_result["deletions"],
                })

            summary["total_files"] += 1

        # Update directory statuses based on children
        dir_statuses = {}
        for entry in entries:
            if entry["is_directory"]:
                continue
            parts = entry["file_path"].split("/")
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                if parent not in dir_statuses:
                    dir_statuses[parent] = set()
                dir_statuses[parent].add(entry["status"])

        for entry in entries:
            if entry["is_directory"] and entry["file_path"] in dir_statuses:
                child_statuses = dir_statuses[entry["file_path"]]
                if child_statuses == {"added"}:
                    entry["status"] = "added"
                elif child_statuses == {"deleted"}:
                    entry["status"] = "deleted"
                elif child_statuses == {"unchanged"}:
                    entry["status"] = "unchanged"
                else:
                    entry["status"] = "modified"

        return summary, entries

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
