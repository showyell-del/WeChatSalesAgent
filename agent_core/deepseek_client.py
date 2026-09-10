import json
import socket
import urllib.error
import urllib.request
from typing import Dict


class DeepSeekError(RuntimeError):
    def __init__(self, code: str, message: str, http_status: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str, timeout: int = 120):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete_json(
        self,
        model: str,
        messages: list,
        max_tokens: int,
        *,
        thinking: bool = False,
        reasoning_effort: str = "high",
    ) -> Dict:
        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled" if thinking else "disabled"},
            "max_tokens": max_tokens,
            "stream": False,
        }
        if thinking:
            payload["reasoning_effort"] = reasoning_effort
        else:
            payload["temperature"] = 0
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("error", {}).get("message", "")
            except json.JSONDecodeError:
                detail = ""
            raise DeepSeekError(
                "DEEPSEEK_HTTP_ERROR", detail or "DeepSeek request failed.", exc.code
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise DeepSeekError(
                    "DEEPSEEK_TIMEOUT",
                    "DeepSeek API did not respond before the configured timeout.",
                ) from exc
            raise DeepSeekError(
                "DEEPSEEK_UNAVAILABLE", "DeepSeek API is unavailable."
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise DeepSeekError(
                "DEEPSEEK_TIMEOUT",
                "DeepSeek API did not respond before the configured timeout.",
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise DeepSeekError(
                "DEEPSEEK_TRANSPORT_INVALID", "DeepSeek response transport failed."
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeepSeekError(
                "DEEPSEEK_RESPONSE_NOT_JSON",
                "DeepSeek response envelope is not valid JSON.",
            ) from exc
        if not isinstance(data, dict):
            raise DeepSeekError(
                "DEEPSEEK_RESPONSE_INVALID", "DeepSeek response envelope is invalid."
            )
        return data

    def list_models(self) -> Dict:
        request = urllib.request.Request(
            self.base_url + "/models",
            headers={"Authorization": "Bearer " + self.api_key},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("error", {}).get("message", "")
            except json.JSONDecodeError:
                detail = ""
            raise DeepSeekError(
                "DEEPSEEK_HTTP_ERROR", detail or "DeepSeek request failed.", exc.code
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise DeepSeekError("DEEPSEEK_TIMEOUT", "DeepSeek API did not respond before the configured timeout.") from exc
            raise DeepSeekError("DEEPSEEK_UNAVAILABLE", "DeepSeek API is unavailable.") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise DeepSeekError("DEEPSEEK_TIMEOUT", "DeepSeek API did not respond before the configured timeout.") from exc
        except (OSError, UnicodeError) as exc:
            raise DeepSeekError("DEEPSEEK_TRANSPORT_INVALID", "DeepSeek response transport failed.") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DeepSeekError("DEEPSEEK_RESPONSE_NOT_JSON", "DeepSeek model list is not valid JSON.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise DeepSeekError("DEEPSEEK_RESPONSE_INVALID", "DeepSeek model list is invalid.")
        return data
