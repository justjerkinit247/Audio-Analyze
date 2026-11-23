from pathlib import Path
import mimetypes
import os
import time
import requests


class LTXError(RuntimeError):
    pass


class LTXClient:
    BASE_URL = "https://api.ltx.io"
    POLL_INTERVAL_SECONDS = 5.0
    MAX_POLL_SECONDS = 1800.0

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

    def _request_upload_slot(self, file_path):
        """Request a presigned upload URL; /v1/upload remains valid for V2 jobs."""
        response = self.session.post(
            f"{self.BASE_URL}/v1/upload",
            headers=self.auth_headers,
            timeout=(20, 180),
        )
        self._check(response, "LTX upload slot request")
        return response.json()

    def _put_signed_upload(self, upload_url, file_path, required_headers=None):
        required_headers = required_headers or {}
        headers = dict(required_headers)
        headers.setdefault("Content-Type", mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")

        with file_path.open("rb") as f:
            response = self.session.put(
                upload_url,
                headers=headers,
                data=f,
                timeout=(20, 300),
            )
        self._check(response, "LTX signed file upload")

    def upload_file(self, file_path):
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        data = self._request_upload_slot(file_path)

        upload_url = data.get("upload_url")
        storage_uri = data.get("storage_uri")
        required_headers = data.get("required_headers") or {}

        if upload_url and storage_uri:
            self._put_signed_upload(upload_url, file_path, required_headers=required_headers)
            return storage_uri

        # Backward-compatible fallback for older/simple upload responses.
        for key in ("uri", "url", "file_url", "asset_url"):
            if isinstance(data.get(key), str):
                return data[key]

        raise LTXError(f"Could not find uploaded file URI in response: {data}")

    def ensure_uri(self, value):
        value = str(value)
        if value.startswith(("http://", "https://", "data:", "ltx://")):
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

    def _submit_async_video(self, endpoint, payload, output_path):
        """Submit a single V2 job, poll it, then download its MP4.

        Never resubmit after receiving a job ID: a status/download failure can
        occur after generation has been billed. The ID is included in errors
        so the existing run report can be used for manual recovery.
        """
        response = self.session.post(
            f"{self.BASE_URL}/v2/{endpoint}",
            headers=self.json_headers,
            json=payload,
            timeout=(20, 120),
        )
        self._check(response, f"LTX {endpoint} submission")
        job = response.json()
        job_id = job.get("id") if isinstance(job, dict) else None
        if not isinstance(job_id, str) or not job_id.strip():
            raise LTXError(
                f"LTX {endpoint} response has no job ID; check the provider "
                "before retrying to avoid a duplicate charge."
            )

        status_url = f"{self.BASE_URL}/v2/{endpoint}/{job_id}"
        deadline = time.monotonic() + self.MAX_POLL_SECONDS
        while True:
            if time.monotonic() >= deadline:
                raise LTXError(
                    f"LTX {endpoint} job {job_id} polling timed out; "
                    "check this job before submitting another."
                )
            time.sleep(self.POLL_INTERVAL_SECONDS)
            poll = self.session.get(
                status_url, headers=self.auth_headers, timeout=(20, 90)
            )
            self._check(poll, f"LTX {endpoint} job {job_id} status")
            state = poll.json()
            if not isinstance(state, dict):
                raise LTXError(f"LTX {endpoint} job {job_id}: invalid status response")
            status = state.get("status")
            if status == "failed":
                error = state.get("error") or {}
                detail = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                raise LTXError(f"LTX {endpoint} job {job_id} failed: {detail}")
            if status == "completed":
                break
            if status not in ("pending", "processing"):
                raise LTXError(
                    f"LTX {endpoint} job {job_id}: unknown status {status!r}"
                )

        video_url = self._extract_video_url(state)
        if not isinstance(video_url, str) or not video_url:
            raise LTXError(f"LTX {endpoint} job {job_id}: missing result.video_url")
        downloaded = self.session.get(video_url, timeout=(20, 300))
        self._check(downloaded, f"LTX {endpoint} job {job_id} download")
        if not downloaded.content:
            raise LTXError(f"LTX {endpoint} job {job_id}: downloaded video is empty")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(downloaded.content)
        return {
            "status": "downloaded",
            "downloaded_mp4": str(output.resolve()),
            "job_id": job_id,
            "api_version": "v2",
        }

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
            return {"status": "dry_run", "endpoint": "/v2/image-to-video", "payload": payload, "output_path": str(Path(output_path).resolve())}
        return self._submit_async_video("image-to-video", payload, output_path)

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
            return {"status": "dry_run", "endpoint": "/v2/audio-to-video", "payload": payload, "output_path": str(Path(output_path).resolve())}
        return self._submit_async_video("audio-to-video", payload, output_path)
