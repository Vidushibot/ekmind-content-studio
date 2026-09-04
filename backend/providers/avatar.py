from abc import ABC, abstractmethod
from pathlib import Path
import time
from uuid import uuid4

import httpx


class AvatarProvider(ABC):
    @abstractmethod
    def create_avatar_scene(self, text: str, output: Path) -> Path: ...
    @abstractmethod
    def get_job_status(self, job_id: str) -> str: ...
    @abstractmethod
    def download_result(self, job_id: str, output: Path) -> Path: ...


class MockAvatarProvider(AvatarProvider):
    def create_avatar_scene(self, text: str, output: Path) -> Path:
        output.write_text("MOCK: no paid avatar provider called", encoding="utf-8"); return output
    def get_job_status(self, job_id: str) -> str: return "MOCK_COMPLETE"
    def download_result(self, job_id: str, output: Path) -> Path: return output


class HeyGenAvatarProvider:
    """Small v3 adapter. Creating a job is deliberately separate from validation."""

    def __init__(self, api_key: str, avatar_id: str, voice_id: str, api_base: str = "https://api.heygen.com") -> None:
        if not all((api_key, avatar_id, voice_id)):
            raise ValueError("HEYGEN_API_KEY, HEYGEN_AVATAR_ID, and HEYGEN_VOICE_ID are required")
        self.api_key = api_key
        self.avatar_id = avatar_id
        self.voice_id = voice_id
        self.api_base = api_base.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "Content-Type": "application/json"}

    @staticmethod
    def _message(response: httpx.Response) -> str:
        try:
            body = response.json()
            return body.get("error", {}).get("message") or body.get("message") or "HeyGen request failed"
        except ValueError:
            return "HeyGen request failed"

    def create_video(self, script: str, title: str, idempotency_key: str | None = None) -> str:
        payload = {"type": "avatar", "avatar_id": self.avatar_id, "title": title[:120], "resolution": "1080p", "aspect_ratio": "16:9", "output_format": "mp4", "script": script, "voice_id": self.voice_id, "caption": {"file_format": "srt", "style": "default"}}
        headers = {**self.headers, "Idempotency-Key": idempotency_key or str(uuid4())}
        response = httpx.post(f"{self.api_base}/v3/videos", headers=headers, json=payload, timeout=60)
        if not response.is_success:
            raise RuntimeError(self._message(response))
        return response.json()["data"]["video_id"]

    def get_video(self, video_id: str) -> dict[str, object]:
        response = httpx.get(f"{self.api_base}/v3/videos/{video_id}", headers=self.headers, timeout=30)
        if not response.is_success:
            raise RuntimeError(self._message(response))
        return response.json()["data"]

    def wait_for_video(self, video_id: str, timeout_seconds: int = 1200) -> dict[str, object]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            result = self.get_video(video_id)
            status = str(result.get("status", "")).lower()
            if status == "completed":
                return result
            if status in {"failed", "error"}:
                raise RuntimeError(str(result.get("failure_message") or "HeyGen rendering failed"))
            time.sleep(10)
        raise RuntimeError("HeyGen rendering timed out after 20 minutes")

    def download(self, url: str, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=120, follow_redirects=True) as response:
            response.raise_for_status()
            with output.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return output
