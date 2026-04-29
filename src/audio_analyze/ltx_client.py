from pathlib import Path
import os
import requests


class LTXError(RuntimeError):
    pass


class LTXClient:
    BASE_URL = "https://api.ltx.video"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("LTXV_API_KEY")
        if not self.api_key:
            raise LTXError("Missing LTXV_API_KEY. Set it in PowerShell before running.")
        self.session = requests.Session()

    @property
    def auth_headers(self):
        return {"Authorization": f"Bearer {self.api_key}"}

    @property
    def json_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _check(self, response, label):
        if response.ok:
            return
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise LTXError(f"{label} failed: HTTP {response.status_code}\n{detail}")

    def upload_file(self, file_path):
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        with file_path.open("rb") as f:
            response = self.session.post(
                f"{self.BASE_URL}/v1/upload",
                headers=self.auth_headers,
                files={"file": (file_path.name, f)},
                timeout=(20, 180),
            )
        self._check(response, "LTX upload")
        data = response.json()
        for key in ("uri", "url", "file_url", "asset_url"):
            if isinstance(data.get(key), str):
                return data[key]
        raise LTXError(f"Could not find uploaded file URI in response: {data}")

    def ensure_uri(self, value):
        value = str(value)
        if value.startswith(("http://", "https://", "data:")):
            return value
        return self.upload_file(value)

    def _extract_video_url(self, data):
        for key in ("url", "video_url", "download_url"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        for key in ("output", "result", "video"):
            value = data.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list) and value and isinstance(value[0], str):
                return value[0]
            if isinstance(value, dict):
                for inner_key in ("url", "video_url", "download_url"):
                    inner_value = value.get(inner_key)
                    if isinstance(inner_value, str):
                        return inner_value
        return None

    def _save_response(self, response, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content_type = response.headers.get("content-type", "").lower()

        if "video" in content_type or "octet-stream" in content_type:
            output_path.write_bytes(response.content)
            return {"status": "downloaded", "downloaded_mp4": str(output_path.resolve())}

        try:
            data = response.json()
        except Exception:
            output_path.write_bytes(response.content)
            return {"status": "saved_raw", "downloaded_mp4": str(output_path.resolve())}

        video_url = self._extract_video_url(data)
        if video_url:
            video_response = self.session.get(video_url, timeout=(20, 180))
            self._check(video_response, "LTX video download")
            output_path.write_bytes(video_response.content)
            data["downloaded_mp4"] = str(output_path.resolve())

        return data

    def image_to_video(self, image_uri, prompt, output_path, model="ltx-2-3-pro", duration=8, resolution="1080x1920", fps=24, guidance_scale=9.0, dry_run=False):
        payload = {
            "image_uri": self.ensure_uri(image_uri) if not dry_run else str(image_uri),
            "prompt": prompt,
            "model": model,
            "duration": duration,
            "resolution": resolution,
            "fps": fps,
            "guidance_scale": guidance_scale,
            "generate_audio": False,
        }
        if dry_run:
            return {"status": "dry_run", "endpoint": "/v1/image-to-video", "payload": payload, "output_path": str(Path(output_path).resolve())}
        response = self.session.post(f"{self.BASE_URL}/v1/image-to-video", headers=self.json_headers, json=payload, timeout=(20, 600))
        self._check(response, "LTX image-to-video")
        return self._save_response(response, output_path)

    def audio_to_video(self, audio_uri, prompt, output_path, image_uri=None, model="ltx-2-3-pro", resolution="1080x1920", guidance_scale=9.0, dry_run=False):
        payload = {
            "audio_uri": self.ensure_uri(audio_uri) if not dry_run else str(audio_uri),
            "prompt": prompt,
            "model": model,
            "resolution": resolution,
            "guidance_scale": guidance_scale,
        }
        if image_uri:
            payload["image_uri"] = self.ensure_uri(image_uri) if not dry_run else str(image_uri)
        if dry_run:
            return {"status": "dry_run", "endpoint": "/v1/audio-to-video", "payload": payload, "output_path": str(Path(output_path).resolve())}
        response = self.session.post(f"{self.BASE_URL}/v1/audio-to-video", headers=self.json_headers, json=payload, timeout=(20, 600))
        self._check(response, "LTX audio-to-video")
        return self._save_response(response, output_path)
