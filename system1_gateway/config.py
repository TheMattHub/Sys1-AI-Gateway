"""Configuration: built-in defaults <- user TOML file <- SYSTEM1_* environment variables."""

import logging
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .providers import REGISTRY
from .providers.base import as_bool


class ConfigError(Exception):
    pass


@dataclass
class Config:
    provider: str = "laya"
    fallback: list = field(default_factory=list)  # disabled by default
    timeout_s: float = 5.0
    min_confidence: float = 0.6
    log_level: str = "INFO"
    log_file: str = ""
    providers: dict = field(default_factory=dict)  # provider name -> settings dict
    routing_enabled: bool = False  # the UserPromptSubmit model-routing hook (route_hook.py)
    # Calibration log: off unless the prompt's working directory is inside one of routing_log_dirs,
    # because it stores prompt text and some repos hold confidential work.
    routing_log_dirs: list = field(default_factory=list)
    routing_log_file: str = "~/.system1-gateway/logs/routing.jsonl"
    routing_min_confidence: float | None = None  # routing's own threshold (set by calibration); None = gateway's
    routing_hint: bool = True  # false: log only, no hint (collection before calibration clears a threshold)
    skills_enabled: bool = False  # the System-1 skill picker (route_hook.pick_skill)
    skills_hint: bool = False  # record-only until calibrated
    skills_min_confidence: float = 0.8  # a wrong skill load costs a whole skill body
    pause_file: str = ""  # set by load_config; when the file exists System-1 is paused (/system1:toggle off)
    source: str = ""  # config file actually read; "" means defaults/env only

    def paused(self) -> bool:
        # Checked on every call, not cached, so a running MCP server obeys the switch without a restart.
        return bool(self.pause_file) and Path(self.pause_file).exists()


def install_dir(env=None) -> Path:
    """Where the installer puts the venv, engines and logs (same rule as hooks/route)."""
    env = os.environ if env is None else env
    return Path(env.get("SYSTEM1_INSTALL_DIR") or Path.home() / ".system1-gateway").expanduser()


def config_path(env=None) -> Path:
    env = os.environ if env is None else env
    if env.get("SYSTEM1_CONFIG"):
        return Path(env["SYSTEM1_CONFIG"]).expanduser()
    if sys.platform == "win32":
        base = env.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    else:
        base = env.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "system1" / "config.toml"


_GATEWAY_ENV = {
    "provider": "SYSTEM1_PROVIDER",
    "fallback": "SYSTEM1_FALLBACK",
    "timeout_s": "SYSTEM1_TIMEOUT_S",
    "min_confidence": "SYSTEM1_MIN_CONFIDENCE",
    "log_level": "SYSTEM1_LOG_LEVEL",
    "log_file": "SYSTEM1_LOG_FILE",
}
_ROUTING_ENV = {
    "enabled": "SYSTEM1_ROUTING_ENABLED",
    "log_dirs": "SYSTEM1_ROUTING_LOG_DIRS",
    "log_file": "SYSTEM1_ROUTING_LOG_FILE",
    "min_confidence": "SYSTEM1_ROUTING_MIN_CONFIDENCE",
    "hint": "SYSTEM1_ROUTING_HINT",
}
_SKILLS_ENV = {
    "enabled": "SYSTEM1_SKILLS_ENABLED",
    "hint": "SYSTEM1_SKILLS_HINT",
    "min_confidence": "SYSTEM1_SKILLS_MIN_CONFIDENCE",
}


def load_config(env=None) -> Config:
    env = os.environ if env is None else env
    path = config_path(env)
    data = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(f"cannot read {path}: {e}") from e
    elif env.get("SYSTEM1_CONFIG"):
        raise ConfigError(f"SYSTEM1_CONFIG points to a missing file: {path}")

    gateway = data.get("gateway", {})
    routing = data.get("routing", {})
    skills = data.get("skills", {})
    providers = data.get("providers", {})
    if not all(isinstance(t, dict) for t in (gateway, routing, skills, providers)) \
            or not all(isinstance(v, dict) for v in providers.values()):
        raise ConfigError(f"{path}: [gateway], [routing], [skills] and [providers.<name>] must be tables")
    for table, values, known in (("gateway", gateway, _GATEWAY_ENV), ("routing", routing, _ROUTING_ENV),
                                 ("skills", skills, _SKILLS_ENV)):
        unknown = set(values) - set(known)
        if unknown:
            raise ConfigError(f"{path}: unknown [{table}] key(s): {', '.join(sorted(unknown))}")
    providers = {name: dict(settings) for name, settings in providers.items()}

    for key, var in _GATEWAY_ENV.items():
        if env.get(var):
            value = env[var]
            gateway[key] = [s.strip() for s in value.split(",") if s.strip()] if key == "fallback" else value
    for key, var in _ROUTING_ENV.items():
        if env.get(var):
            # log_dirs uses the PATH separator (";" on Windows, ":" elsewhere), since paths contain ":".
            routing[key] = [d for d in env[var].split(os.pathsep) if d.strip()] if key == "log_dirs" else env[var]
    for key, var in _SKILLS_ENV.items():
        if env.get(var):
            skills[key] = env[var]
    # Provider settings: SYSTEM1_<PROVIDER>_<KEY>, e.g. SYSTEM1_LAYA_ENDPOINT. Values stay strings.
    for name in REGISTRY:
        prefix = f"SYSTEM1_{name.upper()}_"
        for var, value in env.items():
            if var.upper().startswith(prefix) and len(var) > len(prefix):
                providers.setdefault(name, {})[var[len(prefix):].lower()] = value

    cfg = Config(providers=providers, source=str(path) if path.is_file() else "",
                 pause_file=str(install_dir(env) / "paused"))
    try:
        if "provider" in gateway:
            cfg.provider = str(gateway["provider"]).strip()
        if "fallback" in gateway:
            if not isinstance(gateway["fallback"], list) or not all(isinstance(n, str) for n in gateway["fallback"]):
                raise ValueError("fallback must be a list of provider names")
            cfg.fallback = list(gateway["fallback"])
        if "timeout_s" in gateway:
            cfg.timeout_s = float(gateway["timeout_s"])
        if "min_confidence" in gateway:
            cfg.min_confidence = float(gateway["min_confidence"])
        if "log_level" in gateway:
            cfg.log_level = str(gateway["log_level"]).upper()
        if "log_file" in gateway:
            cfg.log_file = str(gateway["log_file"])
    except (TypeError, ValueError) as e:
        raise ConfigError(f"invalid [gateway] value: {e}") from e
    cfg.routing_enabled = as_bool(routing.get("enabled", False))
    cfg.routing_hint = as_bool(routing.get("hint", True))
    log_dirs = routing.get("log_dirs", [])
    if not isinstance(log_dirs, list) or not all(isinstance(d, str) for d in log_dirs):
        raise ConfigError("[routing] log_dirs must be a list of folder paths")
    cfg.routing_log_dirs = log_dirs
    cfg.routing_log_file = str(routing.get("log_file", cfg.routing_log_file))
    if "min_confidence" in routing:
        try:
            cfg.routing_min_confidence = float(routing["min_confidence"])
        except (TypeError, ValueError) as e:
            raise ConfigError(f"invalid [routing] min_confidence: {e}") from e
        if not 0 <= cfg.routing_min_confidence <= 1:
            raise ConfigError("[routing] min_confidence must be in [0, 1]")

    cfg.skills_enabled = as_bool(skills.get("enabled", False))
    cfg.skills_hint = as_bool(skills.get("hint", False))
    try:
        cfg.skills_min_confidence = float(skills.get("min_confidence", cfg.skills_min_confidence))
    except (TypeError, ValueError) as e:
        raise ConfigError(f"invalid [skills] min_confidence: {e}") from e
    if not 0 <= cfg.skills_min_confidence <= 1:
        raise ConfigError("[skills] min_confidence must be in [0, 1]")

    if not cfg.provider:
        raise ConfigError("provider must be set")
    if not 0 < cfg.timeout_s <= 300:
        raise ConfigError("timeout_s must be in (0, 300]")
    if not 0 <= cfg.min_confidence <= 1:
        raise ConfigError("min_confidence must be in [0, 1]")
    if not isinstance(logging.getLevelName(cfg.log_level), int):
        raise ConfigError(f"unknown log_level {cfg.log_level!r}")
    return cfg
