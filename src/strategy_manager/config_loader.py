"""Unified configuration loader with env var override support.

Load order (highest priority first):
1. Environment variables (MONGO_URI, MONGO_DB, etc.)
2. .env file (config/.env)
3. JSON config file (config/production.json or custom path)
4. Hardcoded defaults

Usage:
    from strategy_manager.config_loader import load_config
    
    # Load with defaults
    cfg = load_config()
    
    # Load from specific config dir
    cfg = load_config(config_dir="/home/user/trading/config")
    
    # Load from specific JSON file
    cfg = load_config(config_file="/etc/strategy-manager/production.json")
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


# Hardcoded defaults (lowest priority)
DEFAULTS = {
    "mongo_uri": "mongodb://localhost:27017",
    "mongo_db": "finance",
    "config_collection": "watchlist_strategies",
    "auto_reload_interval": 60,
    "enable_lifecycle": True,
    "lifecycle": {
        "auto_start": True,
        "auto_stop": True,
        "check_interval_sec": 30,
    },
    "engines": {
        "vnpy": {
            "enabled": True,
        },
        "backtrader": {
            "enabled": False,
        }
    },
    "import_paths": [],
    "log_level": "INFO",
}


def load_config(
    config_dir: Optional[str] = None,
    config_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load configuration with env var override support.
    
    Args:
        config_dir: Path to config directory (default: ./config)
        config_file: Path to JSON config file (overrides config_dir/production.json)
    
    Returns:
        Merged configuration dict
    """
    config = DEFAULTS.copy()
    
    # 1. Load JSON config file
    if config_file and Path(config_file).exists():
        config.update(_load_json_file(config_file))
        logger.info(f"Loaded config from: {config_file}")
    else:
        # Try default location: config/production.json
        config_dir = config_dir or "config"
        default_config_file = Path(config_dir) / "production.json"
        
        if default_config_file.exists():
            config.update(_load_json_file(str(default_config_file)))
            logger.info(f"Loaded config from: {default_config_file}")
        else:
            logger.debug(f"No config file found at {default_config_file}, using defaults")
    
    # 2. Load .env file (if exists)
    config_dir = config_dir or "config"
    env_file = Path(config_dir) / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded .env from: {env_file}")
    else:
        logger.debug(f"No .env file found at {env_file}")
    
    # 3. Override with environment variables (highest priority)
    config = _apply_env_overrides(config)
    
    return config


def _load_json_file(path: str) -> Dict[str, Any]:
    """Load and parse JSON config file."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config file {path}: {e}")
        return {}


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides (highest priority)."""
    # Simple string/int fields
    env_mappings = {
        "MONGO_URI": "mongo_uri",
        "MONGO_DB": "mongo_db",
        "CONFIG_COLLECTION": "config_collection",
        "AUTO_RELOAD_INTERVAL": ("auto_reload_interval", "int"),
        "LOG_LEVEL": "log_level",
    }
    
    for env_key, cfg_key_info in env_mappings.items():
        env_val = os.getenv(env_key)
        if env_val is not None:
            if isinstance(cfg_key_info, tuple):
                cfg_key, val_type = cfg_key_info
                if val_type == "int":
                    try:
                        env_val = int(env_val)
                    except ValueError:
                        logger.warning(f"Invalid int value for {env_key}: {env_val}")
                        continue
            else:
                cfg_key = cfg_key_info
            
            config[cfg_key] = env_val
            logger.debug(f"Override {cfg_key} from env {env_key}")
    
    # Boolean fields (lifecycle)
    lifecycle_flags = {
        "ENABLE_LIFECYCLE": "enable_lifecycle",
    }
    for env_key, cfg_key in lifecycle_flags.items():
        env_val = os.getenv(env_key, "").lower()
        if env_val in ("true", "1", "yes"):
            config[cfg_key] = True
            logger.debug(f"Override {cfg_key} from env {env_key}")
        elif env_val in ("false", "0", "no"):
            config[cfg_key] = False
            logger.debug(f"Override {cfg_key} from env {env_key}")
    
    # Engine enables
    if os.getenv("ENABLE_VNPY"):
        config["engines"]["vnpy"]["enabled"] = os.getenv("ENABLE_VNPY", "").lower() in ("true", "1", "yes")
    if os.getenv("ENABLE_BACKTRADER"):
        config["engines"]["backtrader"]["enabled"] = os.getenv("ENABLE_BACKTRADER", "").lower() in ("true", "1", "yes")
    
    return config


def print_config_sources() -> None:
    """Print where configuration is loaded from (for debugging)."""
    config_dir = "config"
    config_file = Path(config_dir) / "production.json"
    env_file = Path(config_dir) / ".env"
    
    print("\n" + "=" * 80)
    print("Configuration Sources (load order, high to low priority):")
    print("=" * 80)
    print(f"\n1. Environment Variables:")
    print("   • MONGO_URI, MONGO_DB, CONFIG_COLLECTION")
    print("   • AUTO_RELOAD_INTERVAL, LOG_LEVEL")
    print("   • ENABLE_LIFECYCLE, ENABLE_VNPY, ENABLE_BACKTRADER")
    
    print(f"\n2. .env file: {env_file}")
    if env_file.exists():
        print(f"   ✅ Found (will be loaded)")
    else:
        print(f"   ❌ Not found")
    
    print(f"\n3. JSON config: {config_file}")
    if config_file.exists():
        print(f"   ✅ Found (will be loaded)")
    else:
        print(f"   ❌ Not found")
    
    print(f"\n4. Hardcoded defaults: {list(DEFAULTS.keys())}")
    print("=" * 80 + "\n")
