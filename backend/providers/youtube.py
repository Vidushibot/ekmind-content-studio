from pathlib import Path


class YouTubeProvider:
    """Uploads completed videos through the user's YouTube OAuth grant."""

    UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    def _service(self):
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("YouTube dependencies are not installed. Run: pip install -r requirements.txt") from exc
        credentials = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=[self.UPLOAD_SCOPE],
        )
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def upload_private(self, video_path: Path, title: str, description: str) -> dict[str, object]:
        if not video_path.is_file():
            raise ValueError("The approved video file no longer exists")
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise RuntimeError("YouTube dependencies are not installed. Run: pip install -r requirements.txt") from exc
        request = self._service().videos().insert(
            part="snippet,status",
            body={
                "snippet": {"title": title[:100], "description": description[:5000], "categoryId": "27"},
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False},
            },
            media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube accepted the upload but did not return a video ID")
        return {
            "status": "uploaded",
            "privacy_status": "private",
            "video_id": video_id,
            "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        }
