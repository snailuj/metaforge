from fastapi import APIRouter
router = APIRouter()

@router.get("/api/grading/healthz")
def healthz() -> dict:
    """Public probe — used by frontend graceful-degrade.
    No auth, no state leak."""
    return {"ok": True}
