import httpx
import logging
import os
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class MnemoClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
            
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=10.0,
        )

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = endpoint
        if not url.startswith("/"):
            url = "/" + url
            
        retries = 3
        for attempt in range(retries):
            try:
                response = self.client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if 500 <= e.response.status_code < 600 and attempt < retries - 1:
                    continue
                logger.error(f"HTTP error {e.response.status_code} for {method} {url}")
                return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text}
            except httpx.RequestError as e:
                if attempt < retries - 1:
                    continue
                logger.error(f"Request error for {method} {url}: {e}")
                return {"error": "Connection error", "detail": str(e)}
        return {"error": "Max retries exceeded"}

    def get_health(self):
        return self._request("GET", "/health")

    def get_settings(self):
        return self._request("GET", "/settings")
        
    def update_settings(self, updates: dict):
        return self._request("PATCH", "/settings", json=updates)
        
    def validate_settings(self):
        return self._request("GET", "/settings/validate")

    def get_screenshots(self, skip: int = 0, limit: int = 50, filters: dict = None):
        params = {"skip": skip, "limit": limit}
        if filters:
            params.update(filters)
        return self._request("GET", "/screenshots", params=params)

    def get_screenshot(self, screenshot_id: str):
        return self._request("GET", f"/screenshots/{screenshot_id}")

    def analyze_screenshot(self, screenshot_id: str):
        return self._request("POST", f"/screenshots/{screenshot_id}/analyze", json={"force": True})

    def get_folders(self):
        return self._request("GET", "/folders")
        
    def create_folder(self, name: str):
        return self._request("POST", "/folders", json={"name": name, "path": f"/{name}"})

    def update_screenshot_folders(self, screenshot_id: str, folder_ids: list):
        return self._request("PATCH", f"/screenshots/{screenshot_id}/folders", json={"folder_ids": folder_ids})
        
    def get_processing_status(self):
        return self._request("GET", "/processing/status")

    def upload_image(self, file_path: str):
        try:
            with open(file_path, "rb") as f:
                # HTTPX expects files={'file': ('filename', f)}
                files = {"file": (os.path.basename(file_path), f)}
                url = "/screenshots/upload"
                retries = 3
                for attempt in range(retries):
                    try:
                        response = self.client.post(url, files=files)
                        response.raise_for_status()
                        return response.json()
                    except httpx.HTTPStatusError as e:
                        if 500 <= e.response.status_code < 600 and attempt < retries - 1:
                            continue
                        return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text}
                    except httpx.RequestError as e:
                        if attempt < retries - 1:
                            continue
                        return {"error": "Connection error", "detail": str(e)}
                return {"error": "Max retries exceeded"}
        except Exception as e:
            logger.error(f"Error uploading image {file_path}: {e}")
            return {"error": "Upload failed", "detail": str(e)}

    def download_image(self, screenshot_id: str, thumbnail: bool = True) -> bytes | None:
        try:
            url = f"/screenshots/{screenshot_id}/image"
            params = {"thumbnail": str(thumbnail).lower()}
            response = self.client.get(url, params=params)
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Error downloading image {screenshot_id}: {e}")
            return None

    def search(self, query: str, limit: int = 20):
        return self._request("POST", "/search", json={"query": query, "limit": limit})

    def close(self):
        self.client.close()
