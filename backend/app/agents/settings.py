from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.config import settings

_SETTINGS_PATH = Path(__file__).resolve().parent / "agent_settings.yaml"
_CACHE: "AgentSettings | None" = None
_CACHE_MTIME: float | None = None


class TimingConfig(BaseModel):
    silence_trigger_enabled: bool = True
    silence_threshold_seconds: int = 120
    analysis_interval_minutes: int = 5
    warmup_minutes: int = 3
    agent_cooldown_seconds: int = 5
    global_intervention_limit_per_hour: int = 12
    room_auto_intervention_cooldown_seconds: int = 180
    rule_trigger_marker_ttl_seconds: int = 180
    agent_response_timeout_seconds: int = 90


class ThresholdsConfig(BaseModel):
    diversity_score_threshold: float = 0.3
    balance_score_threshold: float = 0.4
    monopoly_message_count: int = 5


class MentionConfig(BaseModel):
    enabled: bool = True
    priority: int = 0
    max_mentions_per_message: int = 1


class AutoSpeakConfig(BaseModel):
    facilitator_silence_enabled: bool = True
    time_progress_enabled: bool = True
    committee_enabled: bool = True
    committee_recent_same_role_window: int = 2
    monopoly_encourager_enabled: bool = True
    committee_devil_advocate_enabled: bool = True
    committee_summarizer_enabled: bool = True
    committee_encourager_enabled: bool = True


class ModelConfigItem(BaseModel):
    model_version: str = settings.AGENT_MODEL
    history_token_budget: int = 4000


class ModelsConfig(BaseModel):
    cognitive_engagement_analyst: ModelConfigItem = Field(default_factory=ModelConfigItem)
    behavioral_engagement_analyst: ModelConfigItem = Field(default_factory=ModelConfigItem)
    emotional_engagement_analyst: ModelConfigItem = Field(default_factory=ModelConfigItem)
    social_engagement_analyst: ModelConfigItem = Field(default_factory=ModelConfigItem)
    chief_dispatcher: ModelConfigItem = Field(default_factory=ModelConfigItem)
    role_agents: ModelConfigItem = Field(default_factory=ModelConfigItem)


class AgentSettings(BaseModel):
    timing: TimingConfig = Field(default_factory=TimingConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    mention: MentionConfig = Field(default_factory=MentionConfig)
    auto_speak: AutoSpeakConfig = Field(default_factory=AutoSpeakConfig)


def get_agent_settings(force_reload: bool = False) -> AgentSettings:
    global _CACHE, _CACHE_MTIME

    try:
        current_mtime = _SETTINGS_PATH.stat().st_mtime
    except FileNotFoundError:
        current_mtime = None

    if (
        not force_reload
        and _CACHE is not None
        and _CACHE_MTIME is not None
        and current_mtime == _CACHE_MTIME
    ):
        return _CACHE

    data = {}
    if _SETTINGS_PATH.exists():
        data = yaml.safe_load(_SETTINGS_PATH.read_text(encoding="utf-8")) or {}

    _CACHE = AgentSettings(**data)
    _CACHE_MTIME = current_mtime
    return _CACHE

