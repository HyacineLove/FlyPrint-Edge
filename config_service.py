from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

import requests

from edge_limits import normalize_local_limits
from logging_utils import VALID_LOG_LEVELS
from print_layout import normalize_scale_percent
from url_scheme import is_http_or_https_url


class ConfigService:
    RESTART_REQUIRED_FIELDS = {
        "network.bind_address",
        "network.port",
    }

    MASKED_FIELDS = {"cloud.credential_blob"}

    def __init__(self, config_repo):
        self.config_repo = config_repo

    def get_public_config(self) -> Dict[str, Any]:
        if not self.config_repo:
            raise ValueError("config_repo is required")
        return self.build_public_config(self.config_repo.get_full_config())

    def build_public_config(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        data = deepcopy(raw)
        cloud = data.setdefault("cloud", {})
        cloud.pop("enabled", None)
        cloud.pop("auto_register", None)
        # Never expose legacy plaintext fields either; a stale file must not
        # turn the local maintenance API into a credential disclosure path.
        cloud.pop("auth_url", None)
        cloud.pop("client_id", None)
        cloud.pop("client_secret", None)
        credential_blob = str(cloud.get("credential_blob") or "")
        cloud.pop("credential_blob", None)
        cloud["activated"] = bool(cloud.get("node_id") and credential_blob)
        settings = data.setdefault("settings", {})
        settings["default_scale_percent"] = normalize_scale_percent(
            settings.get("default_scale_percent"), 100
        )
        settings["copies_min"], settings["copies_max"] = self._normalize_copy_limits(
            settings.get("copies_min"),
            settings.get("copies_max"),
        )
        settings.update(normalize_local_limits(settings))
        settings["log_level"] = str(settings.get("log_level") or "INFO").strip().upper()
        if settings["log_level"] not in VALID_LOG_LEVELS:
            settings["log_level"] = "INFO"
        settings["debug_logging"] = self._normalize_bool(settings.get("debug_logging"))
        data.setdefault("network", {"bind_address": "127.0.0.1", "port": 7860})
        data.pop("printers", None)
        data["meta"] = {
            "restart_required_fields": sorted(self.RESTART_REQUIRED_FIELDS),
            "masked_fields": sorted(self.MASKED_FIELDS),
        }
        return data

    def merge_update(self, raw: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        merged = deepcopy(raw)
        for section in ("cloud", "settings", "network"):
            if section not in update:
                continue
            merged.setdefault(section, {})
            for key, value in update[section].items():
                if section == "cloud" and key not in {"base_url", "node_name", "location", "heartbeat_interval", "verify_ssl"}:
                    continue
                merged[section][key] = value
        merged.setdefault("cloud", {})
        merged["cloud"].pop("enabled", None)
        merged["cloud"].pop("auto_register", None)
        # Remove any legacy plaintext values even if a stale configuration still
        # contains them. They are never a supported input to the new workflow.
        for key in ("auth_url", "client_id", "client_secret"):
            merged["cloud"].pop(key, None)
        return merged

    def classify_changes(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        restart_required: List[str] = []
        applied_now: List[str] = []
        cloud_changed = False

        for dotted_path in self._iter_editable_paths(after):
            before_value = self._get_dotted_value(before, dotted_path)
            after_value = self._get_dotted_value(after, dotted_path)
            if before_value == after_value:
                continue

            if dotted_path.startswith("cloud."):
                cloud_changed = True

            if dotted_path in self.RESTART_REQUIRED_FIELDS:
                restart_required.append(dotted_path)
            else:
                applied_now.append(dotted_path)

        return {
            "restart_required": restart_required,
            "applied_now": applied_now,
            "cloud_changed": cloud_changed,
        }

    def validate(self, raw: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        cloud = raw.get("cloud", {})
        settings = raw.get("settings", {})
        network = raw.get("network", {})

        value = str(cloud.get("base_url") or "").strip()
        if value and not self._is_valid_url(value):
            errors.append("cloud.base_url must be a valid URL")

        try:
            heartbeat = int(cloud.get("heartbeat_interval", 30))
            if heartbeat <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("cloud.heartbeat_interval must be a positive integer")

        if settings.get("default_scale_percent") not in (None, ""):
            try:
                scale_percent = int(settings["default_scale_percent"])
                if scale_percent < 50 or scale_percent > 150 or scale_percent % 10 != 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append("settings.default_scale_percent must be an integer from 50 to 150 in 10 percent steps")

        if settings.get("log_level") not in (None, "", *VALID_LOG_LEVELS):
            errors.append("settings.log_level must be DEBUG, INFO, WARNING, or ERROR")

        if settings.get("debug_logging") not in (None, "", True, False):
            errors.append("settings.debug_logging must be a boolean")

        for key in ("max_file_size_bytes", "max_document_pages", "max_list_items"):
            value = settings.get(key)
            if value in (None, ""):
                continue
            try:
                if int(value) < 0 or isinstance(value, float) and not value.is_integer():
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"settings.{key} must be an integer >= 0")

        copies_min = 1
        if settings.get("copies_min") not in (None, ""):
            try:
                copies_min = int(settings["copies_min"])
                if copies_min < 1:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append("settings.copies_min must be an integer >= 1")
                copies_min = 1

        if settings.get("copies_max") not in (None, ""):
            try:
                copies_max = int(settings["copies_max"])
                if copies_max < copies_min:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append("settings.copies_max must be an integer and >= settings.copies_min")

        if not str(network.get("bind_address") or "").strip():
            errors.append("network.bind_address must not be empty")
        else:
            bind_address = str(network.get("bind_address")).strip()
            if bind_address not in {"127.0.0.1", "::1"}:
                errors.append("network.bind_address must be loopback-only")

        try:
            port = int(network.get("port", 7860))
            if port < 1 or port > 65535:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("network.port must be a valid port")

        return errors

    def save_and_apply(self, update: Dict[str, Any], cloud_service=None) -> Dict[str, Any]:
        if not self.config_repo:
            return {"success": False, "saved": False, "errors": ["config repository unavailable"]}

        current = self.config_repo.get_full_config()
        merged = self.merge_update(current, update)
        errors = self.validate(merged)
        if errors:
            return {"success": False, "saved": False, "errors": errors}

        changes = self.classify_changes(current, merged)

        # Cloud 配置预检必须在落盘前：无效配置不写盘，避免磁盘/运行时状态分叉
        cloud_reconnected = False
        warnings: List[str] = []
        if changes["cloud_changed"] and cloud_service:
            preflight = self.test_cloud_connection({"cloud": merged.get("cloud", {})})
            if not preflight.get("success"):
                return {
                    "success": False,
                    "saved": False,
                    "errors": [preflight.get("message") or "cloud configuration test failed"],
                }

        self.config_repo.replace_full_config(merged)

        if changes["cloud_changed"] and cloud_service:
            result = cloud_service.reconfigure(merged.get("cloud", {}), preserve_node_id=True)
            cloud_reconnected = bool(result.get("connected"))
            if not result.get("success"):
                # 运行时应用失败：回滚磁盘配置到变更前
                self.config_repo.replace_full_config(current)
                warnings.append(result.get("message") or "cloud reconfigure failed")
            elif result.get("registered") is False:
                warnings.append("\u4e91\u7aef\u914d\u7f6e\u5df2\u5e94\u7528\uff0c\u8bf7\u6267\u884c\u201c\u68c0\u6d4b\u8fde\u63a5\u5e76\u6ce8\u518c\u8282\u70b9\u201d\u5b8c\u6210\u8bbe\u7f6e")
            elif not cloud_reconnected:
                warnings.append(result.get("message") or "\u4e91\u7aef\u8fd0\u884c\u65f6\u5df2\u91cd\u8f7d")

        return {
            "success": True,
            "saved": True,
            "applied_now": changes["applied_now"],
            "restart_required": changes["restart_required"],
            "cloud_reconnected": cloud_reconnected,
            "warnings": warnings,
            "errors": [],
        }

    def test_cloud_connection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.config_repo:
            current = self.config_repo.get_full_config()
            merged = self.merge_update(current, payload)
            cloud = merged.get("cloud", {})
        else:
            cloud = payload.get("cloud", {})
        errors = self.validate({"cloud": cloud, "settings": {}, "network": {"bind_address": "127.0.0.1", "port": 7860}})
        if errors:
            return {"success": False, "message": "; ".join(errors)}

        base_url = str(cloud.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            return {"success": True, "message": "\u6821\u9a8c\u901a\u8fc7"}

        try:
            response = requests.get(
                f"{base_url}/api/v1/health",
                verify=bool(cloud.get("verify_ssl", True)),
                timeout=5,
            )
            if response.status_code >= 400:
                return {"success": False, "message": f"\u4e91\u7aef\u5065\u5eb7\u68c0\u67e5\u5931\u8d25: {response.status_code}"}
        except Exception as exc:
            return {"success": False, "message": f"\u4e91\u7aef\u5065\u5eb7\u68c0\u67e5\u5f02\u5e38: {exc}"}

        return {"success": True, "message": "\u6821\u9a8c\u901a\u8fc7"}

    def _iter_editable_paths(self, config: Dict[str, Any]) -> List[str]:
        paths: List[str] = []
        for section in ("cloud", "settings", "network", "printers"):
            for key in config.get(section, {}):
                if section == "cloud" and key in {"node_id", "credential_blob", "profile_pending", "activated"}:
                    continue
                paths.append(f"{section}.{key}")
        return paths

    def _get_dotted_value(self, data: Dict[str, Any], dotted_path: str) -> Any:
        current: Any = data
        for part in dotted_path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _is_valid_url(self, value: str) -> bool:
        return is_http_or_https_url(value)

    def _normalize_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _normalize_optional_positive_number(self, value: Any) -> Any:
        if value in (None, ""):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        return number if number > 0 else ""

    def _normalize_copy_limits(self, copies_min: Any, copies_max: Any) -> tuple[int, int]:
        normalized_min = self._normalize_copy_limit(copies_min, default=1, minimum=1)
        normalized_max = self._normalize_copy_limit(copies_max, default=3, minimum=normalized_min)
        return normalized_min, max(normalized_min, normalized_max)

    def _normalize_copy_limit(self, value: Any, default: int, minimum: int) -> int:
        if value in (None, ""):
            return max(minimum, default)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return max(minimum, default)
        return max(minimum, parsed)
