"""Fixed host voice assets for game narration."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/voice/host/fixed", tags=["voice"])

HOST_FIXED_VOICE_FILES = {
    "dawn_peaceful_night": "dawn_peaceful_night.mp3",
    "day_no_exile": "day_no_exile.mp3",
    "day_speech_start": "day_speech_start.mp3",
    "day_vote_generic": "day_vote_generic.mp3",
    "day_vote_start": "day_vote_start.mp3",
    "exile_pk_speech_start": "exile_pk_speech_start.mp3",
    "exile_pk_vote_generic": "exile_pk_vote_generic.mp3",
    "exile_pk_vote_start": "exile_pk_vote_start.mp3",
    "hunter_close_eyes": "hunter_close_eyes.mp3",
    "hunter_open_confirm_identity": "hunter_open_confirm_identity.mp3",
    "hunter_shot_prompt": "hunter_shot_prompt.mp3",
    "idiot_close_eyes": "idiot_close_eyes.mp3",
    "idiot_open_confirm_identity": "idiot_open_confirm_identity.mp3",
    "idiot_reveal_prompt": "idiot_reveal_prompt.mp3",
    "night_close_eyes": "night_close_eyes.mp3",
    "round_end_night_close_eyes": "round_end_night_close_eyes.mp3",
    "seer_close_eyes": "seer_close_eyes.mp3",
    "seer_open_check_player": "seer_open_check_player.mp3",
    "sheriff_badge_lost": "sheriff_badge_lost.mp3",
    "sheriff_candidate_collect": "sheriff_candidate_collect.mp3",
    "sheriff_election_start": "sheriff_election_start.mp3",
    "sheriff_pk_vote_generic": "sheriff_pk_vote_generic.mp3",
    "sheriff_pk_vote_start": "sheriff_pk_vote_start.mp3",
    "sheriff_speech_start": "sheriff_speech_start.mp3",
    "sheriff_vote_finished": "sheriff_vote_finished.mp3",
    "sheriff_vote_generic": "sheriff_vote_generic.mp3",
    "sheriff_vote_start": "sheriff_vote_start.mp3",
    "sheriff_vote_tied_pk_speech": "sheriff_vote_tied_pk_speech.mp3",
    "villagers_win": "villagers_win.mp3",
    "werewolves_win": "werewolves_win.mp3",
    "witch_close_eyes": "witch_close_eyes.mp3",
    "witch_open_use_medicine": "witch_open_use_medicine.mp3",
    "wolf_close_eyes": "wolf_close_eyes.mp3",
    "wolf_open_choose_target": "wolf_open_choose_target.mp3",
    "wolf_unify_target": "wolf_unify_target.mp3",
}


def _resolve_fixed_voice_dir() -> Path:
    """Find fixed host voice assets in local dev and the backend image."""
    current_file = Path(__file__).resolve()
    candidates = [
        current_file.parents[2] / "data" / "voice" / "host" / "fixed",
        current_file.parents[3] / "data" / "voice" / "host" / "fixed",
    ]
    for candidate in candidates:
        if all((candidate / filename).is_file() for filename in HOST_FIXED_VOICE_FILES.values()):
            return candidate
    return candidates[0]


_FIXED_VOICE_DIR = _resolve_fixed_voice_dir()


@router.get("/manifest")
async def host_voice_manifest(request: Request) -> dict[str, dict[str, str]]:
    """Return whitelisted fixed host voice URLs."""
    return {
        "voices": {
            key: str(request.url_for("get_fixed_host_voice_asset", voice_key=key))
            for key in HOST_FIXED_VOICE_FILES
        }
    }


@router.get("/{voice_key}.mp3", response_class=FileResponse, name="get_fixed_host_voice_asset")
async def get_fixed_host_voice_asset(voice_key: str) -> FileResponse:
    """Return a whitelisted fixed host voice asset."""
    filename = HOST_FIXED_VOICE_FILES.get(voice_key)
    if filename is None:
        raise HTTPException(status_code=404, detail="Unknown fixed host voice asset.")
    path = _FIXED_VOICE_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fixed host voice asset not found.")
    return FileResponse(path, media_type="audio/mpeg", filename=filename)
