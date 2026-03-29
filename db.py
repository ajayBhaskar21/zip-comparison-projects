"""SQLite database setup and CRUD operations."""

import aiosqlite
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "comparisons.db")


async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS comparisons (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                modified_filename TEXT NOT NULL,
                summary_json TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS diff_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comparison_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                diff_text TEXT,
                old_size INTEGER,
                new_size INTEGER,
                is_binary INTEGER DEFAULT 0,
                is_directory INTEGER DEFAULT 0,
                additions INTEGER DEFAULT 0,
                deletions INTEGER DEFAULT 0,
                FOREIGN KEY (comparison_id) REFERENCES comparisons(id) ON DELETE CASCADE
            )
        """)
        await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()


async def save_comparison(comparison_id: str, created_at: str,
                          original_filename: str, modified_filename: str,
                          summary: dict, entries: list[dict]):
    """Save a comparison result to the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO comparisons (id, created_at, original_filename, modified_filename, summary_json) VALUES (?, ?, ?, ?, ?)",
            (comparison_id, created_at, original_filename, modified_filename, json.dumps(summary))
        )
        for entry in entries:
            await db.execute(
                """INSERT INTO diff_entries
                   (comparison_id, file_path, status, diff_text, old_size, new_size, is_binary, is_directory, additions, deletions)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    comparison_id,
                    entry["file_path"],
                    entry["status"],
                    entry.get("diff_text"),
                    entry.get("old_size"),
                    entry.get("new_size"),
                    1 if entry.get("is_binary") else 0,
                    1 if entry.get("is_directory") else 0,
                    entry.get("additions", 0),
                    entry.get("deletions", 0),
                )
            )
        await db.commit()


async def get_comparisons():
    """List all comparisons."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, created_at, original_filename, modified_filename, summary_json FROM comparisons ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "original_filename": row["original_filename"],
                "modified_filename": row["modified_filename"],
                "summary": json.loads(row["summary_json"]),
            })
        return results


async def get_comparison(comparison_id: str):
    """Get a single comparison with all its diff entries."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT id, created_at, original_filename, modified_filename, summary_json FROM comparisons WHERE id = ?",
            (comparison_id,)
        )
        comp = await cursor.fetchone()
        if not comp:
            return None

        cursor = await db.execute(
            "SELECT file_path, status, diff_text, old_size, new_size, is_binary, is_directory, additions, deletions FROM diff_entries WHERE comparison_id = ? ORDER BY file_path",
            (comparison_id,)
        )
        entries = await cursor.fetchall()

        return {
            "id": comp["id"],
            "created_at": comp["created_at"],
            "original_filename": comp["original_filename"],
            "modified_filename": comp["modified_filename"],
            "summary": json.loads(comp["summary_json"]),
            "entries": [
                {
                    "file_path": e["file_path"],
                    "status": e["status"],
                    "diff_text": e["diff_text"],
                    "old_size": e["old_size"],
                    "new_size": e["new_size"],
                    "is_binary": bool(e["is_binary"]),
                    "is_directory": bool(e["is_directory"]),
                    "additions": e["additions"],
                    "deletions": e["deletions"],
                }
                for e in entries
            ],
        }


async def delete_comparison(comparison_id: str):
    """Delete a comparison and its entries."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM comparisons WHERE id = ?", (comparison_id,))
        await db.commit()
