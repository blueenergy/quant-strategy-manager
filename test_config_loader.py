"""Test config loader with env variable override."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from strategy_manager.config_loader import load_config, print_config_sources


def test_config_loading():
    """Test different config loading scenarios."""
    
    print("\n" + "=" * 80)
    print("TEST 1: Config sources with defaults")
    print("=" * 80)
    print_config_sources()
    
    print("\nTEST 2: Load config (should use defaults)")
    config = load_config(config_dir="config")
    print(f"mongo_uri: {config.get('mongo_uri')}")
    print(f"mongo_db: {config.get('mongo_db')}")
    print(f"enable_lifecycle: {config.get('enable_lifecycle')}")
    
    print("\n" + "=" * 80)
    print("TEST 3: Override with environment variables")
    print("=" * 80)
    
    # Set env vars
    os.environ["MONGO_URI"] = "mongodb://prod-mongo:27017"
    os.environ["MONGO_DB"] = "prod_finance"
    os.environ["ENABLE_LIFECYCLE"] = "false"
    
    config = load_config(config_dir="config")
    print(f"mongo_uri (should be overridden): {config.get('mongo_uri')}")
    print(f"mongo_db (should be overridden): {config.get('mongo_db')}")
    print(f"enable_lifecycle (should be False): {config.get('enable_lifecycle')}")
    
    assert config.get('mongo_uri') == "mongodb://prod-mongo:27017", "MONGO_URI env override failed"
    assert config.get('mongo_db') == "prod_finance", "MONGO_DB env override failed"
    assert config.get('enable_lifecycle') == False, "ENABLE_LIFECYCLE env override failed"
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_config_loading()
