"""
config.py — Centralised, typed configuration for the Women Safety Product.

All settings are loaded from the .env file (or OS environment).
Import `cfg` anywhere in the project:

    from config import cfg
    print(cfg.MODEL_PATH)

Design notes:
- Uses python-dotenv for .env parsing.
- All values are validated / cast at startup; a bad value fails loudly.
- Adding a new setting = one line here + one line in .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from the project root (the directory that contains config.py)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env", override=True)


def _env(key: str, default: str = "") -> str:
    """Return stripped string value from environment."""
    return os.environ.get(key, default).strip()


def _bool(key: str, default: bool = False) -> bool:
    """Parse boolean env var (true/1/yes → True)."""
    return _env(key, str(default)).lower() in {"true", "1", "yes"}


def _int(key: str, default: int = 0) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError as exc:
        raise ValueError(f"[config] {key} must be an integer, got '{_env(key)}'") from exc


def _float(key: str, default: float = 0.0) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError as exc:
        raise ValueError(f"[config] {key} must be a float, got '{_env(key)}'") from exc


# ---------------------------------------------------------------------------
# Dataclass — one field per .env variable
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Config:
    # Project root (always available)
    PROJECT_ROOT: Path = field(default=_PROJECT_ROOT)

    # --- Camera ---
    CAMERA_SOURCE: str = field(default_factory=lambda: _env("CAMERA_SOURCE", "0"))
    CAMERA_WIDTH: int = field(default_factory=lambda: _int("CAMERA_WIDTH", 640))
    CAMERA_HEIGHT: int = field(default_factory=lambda: _int("CAMERA_HEIGHT", 480))
    CAMERA_FPS: int = field(default_factory=lambda: _int("CAMERA_FPS", 30))
    CAMERA_RECONNECT_DELAY: int = field(default_factory=lambda: _int("CAMERA_RECONNECT_DELAY", 3))
    CAMERA_MAX_RECONNECT: int = field(default_factory=lambda: _int("CAMERA_MAX_RECONNECT", 10))

    # --- Model ---
    MODEL_PATH: str = field(default_factory=lambda: _env("MODEL_PATH", "models/yolov8n.pt"))
    MODEL_CONFIDENCE: float = field(default_factory=lambda: _float("MODEL_CONFIDENCE", 0.45))
    MODEL_IOU: float = field(default_factory=lambda: _float("MODEL_IOU", 0.5))
    MODEL_DEVICE: str = field(default_factory=lambda: _env("MODEL_DEVICE", "cpu"))
    MODEL_IMGSZ: int = field(default_factory=lambda: _int("MODEL_IMGSZ", 640))
    EXPORT_ONNX: bool = field(default_factory=lambda: _bool("EXPORT_ONNX", False))

    # --- Tracking ---
    TRACKER_CONFIG: str = field(default_factory=lambda: _env("TRACKER_CONFIG", "botsort.yaml"))
    TRACKER_PERSIST: bool = field(default_factory=lambda: _bool("TRACKER_PERSIST", True))

    # --- Threat Engine ---
    THREAT_MODEL_PATH: str = field(
        default_factory=lambda: _env("THREAT_MODEL_PATH", "models/threat_xgb.json")
    )
    THREAT_LOW: float = field(default_factory=lambda: _float("THREAT_LOW", 0.35))
    THREAT_MEDIUM: float = field(default_factory=lambda: _float("THREAT_MEDIUM", 0.60))
    THREAT_HIGH: float = field(default_factory=lambda: _float("THREAT_HIGH", 0.80))
    THREAT_SUSTAINED_FRAMES: int = field(
        default_factory=lambda: _int("THREAT_SUSTAINED_FRAMES", 15)
    )
    THREAT_MIN_GROUP_SIZE: int = field(
        default_factory=lambda: _int("THREAT_MIN_GROUP_SIZE", 2)
    )

    # --- Interaction Analysis ---
    ENABLE_INTERACTION_ANALYSIS: bool = field(
        default_factory=lambda: _bool("ENABLE_INTERACTION_ANALYSIS", True)
    )
    INTERACTION_DISTANCE_THRESHOLD: float = field(
        default_factory=lambda: _float("INTERACTION_DISTANCE_THRESHOLD", 0.25)
    )
    INTERACTION_BOOST_MAX: float = field(
        default_factory=lambda: _float("INTERACTION_BOOST_MAX", 0.25)
    )

    # --- Alerts ---
    ALERT_EMAIL_ENABLED: bool = field(default_factory=lambda: _bool("ALERT_EMAIL_ENABLED", False))
    ALERT_EMAIL_SMTP: str = field(
        default_factory=lambda: _env("ALERT_EMAIL_SMTP", "smtp.gmail.com")
    )
    ALERT_EMAIL_PORT: int = field(default_factory=lambda: _int("ALERT_EMAIL_PORT", 587))
    ALERT_EMAIL_SENDER: str = field(default_factory=lambda: _env("ALERT_EMAIL_SENDER", ""))
    ALERT_EMAIL_PASSWORD: str = field(default_factory=lambda: _env("ALERT_EMAIL_PASSWORD", ""))
    ALERT_EMAIL_RECEIVER: str = field(default_factory=lambda: _env("ALERT_EMAIL_RECEIVER", ""))
    ALERT_SOUND_ENABLED: bool = field(default_factory=lambda: _bool("ALERT_SOUND_ENABLED", True))
    ALERT_COOLDOWN: int = field(default_factory=lambda: _int("ALERT_COOLDOWN", 60))

    # --- Location ---
    LOCATION_GOOGLE_API_KEY: str = field(
        default_factory=lambda: _env("LOCATION_GOOGLE_API_KEY", "")
    )
    LOCATION_IP_FALLBACK: bool = field(
        default_factory=lambda: _bool("LOCATION_IP_FALLBACK", True)
    )

    # --- Dashboard ---
    DASHBOARD_PORT: int = field(default_factory=lambda: _int("DASHBOARD_PORT", 8501))
    DASHBOARD_REFRESH_MS: int = field(default_factory=lambda: _int("DASHBOARD_REFRESH_MS", 100))
    LOG_MAX_ROWS: int = field(default_factory=lambda: _int("LOG_MAX_ROWS", 200))

    # --- Logging ---
    LOG_LEVEL: str = field(default_factory=lambda: _env("LOG_LEVEL", "DEBUG"))
    LOG_DIR: str = field(default_factory=lambda: _env("LOG_DIR", "logs"))
    LOG_ROTATION: str = field(default_factory=lambda: _env("LOG_ROTATION", "10 MB"))
    LOG_RETENTION: str = field(default_factory=lambda: _env("LOG_RETENTION", "7 days"))

    # -----------------------------------------------------------------------
    # Derived helpers (computed properties on frozen dataclass via __post_init__)
    # -----------------------------------------------------------------------
    def __post_init__(self) -> None:
        # Ensure CAMERA_SOURCE is cast to int when it represents a webcam index
        # We bypass frozen=True via object.__setattr__ for this one derived field.
        raw = self.CAMERA_SOURCE
        if raw.lstrip("-").isdigit():
            object.__setattr__(self, "CAMERA_SOURCE", int(raw))

    @property
    def model_abs_path(self) -> Path:
        """Absolute path to the YOLO model file."""
        p = Path(self.MODEL_PATH)
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def threat_model_abs_path(self) -> Path:
        """Absolute path to the XGBoost threat model file."""
        p = Path(self.THREAT_MODEL_PATH)
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    @property
    def log_abs_dir(self) -> Path:
        """Absolute path to the logging directory."""
        p = Path(self.LOG_DIR)
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    def display(self) -> str:
        """Return a human-readable summary of active config (masks secrets)."""
        lines = ["=" * 60, "  Women Safety Product — Active Configuration", "=" * 60]
        for f_name, f_val in self.__dict__.items():
            # Mask sensitive fields
            if any(s in f_name.upper() for s in ["PASSWORD", "API_KEY", "SECRET"]):
                f_val = "***"
            lines.append(f"  {f_name:<35} {f_val}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Singleton instance — import this everywhere
# ---------------------------------------------------------------------------
cfg = Config()

if __name__ == "__main__":
    print(cfg.display())


# ---------------------------------------------------------------------------
# AlertConfig — Twilio / Africa's Talking settings (used by twilio_alerts.py)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AlertConfig:
    # --- Twilio ---
    TWILIO_ENABLED: bool = field(default_factory=lambda: _bool("TWILIO_ENABLED", False))
    TWILIO_ACCOUNT_SID: str = field(default_factory=lambda: _env("TWILIO_ACCOUNT_SID", "ACxxx"))
    TWILIO_AUTH_TOKEN: str = field(default_factory=lambda: _env("TWILIO_AUTH_TOKEN", "your_auth_token_here"))
    TWILIO_FROM_NUMBER: str = field(default_factory=lambda: _env("TWILIO_FROM_NUMBER", ""))
    TWILIO_TO_NUMBERS: str = field(default_factory=lambda: _env("TWILIO_TO_NUMBERS", ""))   # comma-separated

    # Twilio channels
    TWILIO_SMS_ENABLED: bool = field(default_factory=lambda: _bool("TWILIO_SMS_ENABLED", True))
    TWILIO_VOICE_ENABLED: bool = field(default_factory=lambda: _bool("TWILIO_VOICE_ENABLED", False))
    TWILIO_WHATSAPP_ENABLED: bool = field(default_factory=lambda: _bool("TWILIO_WHATSAPP_ENABLED", False))
    TWILIO_WHATSAPP_FROM: str = field(
        default_factory=lambda: _env("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    )
    TWILIO_VOICE_LANGUAGE: str = field(
        default_factory=lambda: _env("TWILIO_VOICE_LANGUAGE", "en-IN")
    )

    # Which threat levels trigger each channel
    SMS_ON_LEVELS: str = field(
        default_factory=lambda: _env("SMS_ON_LEVELS", "HIGH,MEDIUM")
    )
    CALL_ON_LEVELS: str = field(
        default_factory=lambda: _env("CALL_ON_LEVELS", "HIGH")
    )
    WHATSAPP_ON_LEVELS: str = field(
        default_factory=lambda: _env("WHATSAPP_ON_LEVELS", "HIGH,MEDIUM")
    )

    # --- Africa's Talking (free SMS fallback) ---
    AFRICASTALKING_ENABLED: bool = field(
        default_factory=lambda: _bool("AFRICASTALKING_ENABLED", False)
    )
    AFRICASTALKING_USERNAME: str = field(
        default_factory=lambda: _env("AFRICASTALKING_USERNAME", "sandbox")
    )
    AFRICASTALKING_API_KEY: str = field(
        default_factory=lambda: _env("AFRICASTALKING_API_KEY", "your_api_key_here")
    )
    AFRICASTALKING_FROM: str = field(
        default_factory=lambda: _env("AFRICASTALKING_FROM", "")
    )

    # ── Computed helpers ──────────────────────────────────────────────────────

    @property
    def to_numbers(self) -> list:
        """Return list of cleaned E.164 recipient phone numbers."""
        raw = self.TWILIO_TO_NUMBERS
        return [n.strip() for n in raw.split(",") if n.strip()]

    @property
    def sms_levels(self) -> list:
        return [l.strip() for l in self.SMS_ON_LEVELS.split(",") if l.strip()]

    @property
    def call_levels(self) -> list:
        return [l.strip() for l in self.CALL_ON_LEVELS.split(",") if l.strip()]

    @property
    def whatsapp_levels(self) -> list:
        return [l.strip() for l in self.WHATSAPP_ON_LEVELS.split(",") if l.strip()]


# Singleton — imported by twilio_alerts.py
alert_cfg = AlertConfig()

