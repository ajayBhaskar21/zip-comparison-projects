"""FastAPI application for ZIP file comparison."""

import os
import uuid
import tempfile
import shutil
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db import init_db, save_comparison, get_comparisons, get_comparison, delete_comparison
from differ import compare_zips
from models import ComparisonResult, ComparisonListItem, ComparisonSummary, DiffEntry


MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="ZIP Comparison API",
    description="Upload two ZIP files and compare their contents.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/compare", response_model=ComparisonResult)
async def compare_zips_endpoint(
    original: UploadFile = File(..., description="The original ZIP file"),
    modified: UploadFile = File(..., description="The modified ZIP file"),
):
    """Upload two ZIP files and compare their contents."""
    # Validate file types
    for f, label in [(original, "original"), (modified, "modified")]:
        if not f.filename.lower().endswith(".zip"):
            raise HTTPException(
                status_code=400,
                detail=f"The {label} file must be a .zip file. Got: {f.filename}"
            )

    # Save uploaded files to temp
    temp_dir = tempfile.mkdtemp()
    try:
        zip1_path = os.path.join(temp_dir, "original.zip")
        zip2_path = os.path.join(temp_dir, "modified.zip")

        # Read and save with size check
        for path, f, label in [(zip1_path, original, "original"), (zip2_path, modified, "modified")]:
            content = await f.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"The {label} file exceeds the {MAX_UPLOAD_SIZE // (1024*1024)}MB size limit."
                )
            with open(path, "wb") as out:
                out.write(content)

        # Run comparison
        summary, entries = compare_zips(zip1_path, zip2_path)

        # Save to database
        comparison_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        await save_comparison(
            comparison_id=comparison_id,
            created_at=created_at,
            original_filename=original.filename,
            modified_filename=modified.filename,
            summary=summary,
            entries=entries,
        )

        return ComparisonResult(
            id=comparison_id,
            created_at=created_at,
            original_filename=original.filename,
            modified_filename=modified.filename,
            summary=ComparisonSummary(**summary),
            entries=[DiffEntry(**e) for e in entries],
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.get("/api/comparisons", response_model=list[ComparisonListItem])
async def list_comparisons():
    """List all past comparisons."""
    rows = await get_comparisons()
    return [
        ComparisonListItem(
            id=r["id"],
            created_at=r["created_at"],
            original_filename=r["original_filename"],
            modified_filename=r["modified_filename"],
            summary=ComparisonSummary(**r["summary"]),
        )
        for r in rows
    ]


@app.get("/api/comparisons/{comparison_id}", response_model=ComparisonResult)
async def get_comparison_endpoint(comparison_id: str):
    """Get a specific comparison result."""
    result = await get_comparison(comparison_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comparison not found.")
    return ComparisonResult(
        id=result["id"],
        created_at=result["created_at"],
        original_filename=result["original_filename"],
        modified_filename=result["modified_filename"],
        summary=ComparisonSummary(**result["summary"]),
        entries=[DiffEntry(**e) for e in result["entries"]],
    )


@app.delete("/api/comparisons/{comparison_id}")
async def delete_comparison_endpoint(comparison_id: str):
    """Delete a comparison."""
    result = await get_comparison(comparison_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comparison not found.")
    await delete_comparison(comparison_id)
    return {"detail": "Comparison deleted."}
