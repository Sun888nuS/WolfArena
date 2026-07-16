"""Background audio assets for the game client."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/voice/background", tags=["voice"])

_AUDIO_FILES = {
    "day": "day.mp3",
    "night": "night.mp3",
    "vote": "vote.mp3",
}


def _resolve_data_dir() -> Path:
    """Find the shared data directory in local dev and the backend image."""
    current_file = Path(__file__).resolve()
    candidates = [
        current_file.parents[2] / "data",  # /app/data in the Docker image.
        current_file.parents[3] / "data",  # repo-root/data in local dev.
    ]
    for candidate in candidates:
        if all((candidate / filename).is_file() for filename in _AUDIO_FILES.values()):
            return candidate
    return candidates[0]


_DATA_DIR = _resolve_data_dir()


@router.get("/manifest")
async def background_audio_manifest(request: Request) -> dict[str, dict[str, str]]:
    """Return whitelisted background audio URLs."""
    return {
        "tracks": {
            track: str(request.url_for("get_background_audio_asset", track=track))
            for track in _AUDIO_FILES
        }
    }


@router.get("/{track}.mp3", response_class=FileResponse, name="get_background_audio_asset")
async def get_background_audio_asset(track: str) -> FileResponse:
    """Return a whitelisted background audio asset."""
    filename = _AUDIO_FILES.get(track)
    if filename is None:
        raise HTTPException(status_code=404, detail="Unknown background audio asset.")
    path = _DATA_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Background audio asset not found.")
    return FileResponse(path, media_type="audio/mpeg", filename=filename)
