"""Command-line interface for strategy manager.

This is the main entry point when using strategy_manager as a framework.

Usage:
    # Start all strategies from database
    python -m strategy_manager.cli start
    
    # Start with specific config
    python -m strategy_manager.cli start --config prod.json
    
    # Stop gracefully
    python -m strategy_manager.cli stop
    
    # Check status
    python -m strategy_manager.cli status
"""

import argparse
import signal
import sys
import time
import logging
import json
import os

from .core import MultiStrategyOrchestrator, LifecycleManager
from .adapters import create_vnpy_worker
from .config_loader import load_config as load_config_with_env


def setup_logging(level: str = "INFO"):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def cmd_start(args):
    """Start strategy manager."""
    print("=" * 80)
    print("Strategy Manager - Starting")
    print("=" * 80)
    
    # Load configuration (env vars > JSON > defaults)
    config = load_config_with_env(config_file=args.config)
    
    print(f"MongoDB: {config['mongo_uri']}")
    print(f"Database: {config['mongo_db']}")
    print(f"Collection: {config['config_collection']}")
    print("sys.path:", sys.path)
    
    # Add import paths for user strategies
    import_paths = config.get("import_paths", [])
    print("\n--- Path Diagnostics ---")
    print(f"Current Working Directory: {os.getcwd()}")
    print(f"Found import_paths in config: {import_paths}")
    for path in import_paths:
        # Ensure path is absolute to avoid ambiguity
        absolute_path = os.path.abspath(path)
        if absolute_path not in sys.path:
            sys.path.insert(0, absolute_path)
            print(f"✅ Added to sys.path: {absolute_path}")
        else:
            print(f"☑️  Already in sys.path: {absolute_path}")

    print("\nFinal sys.path for module resolution:")
    import pprint
    pprint.pprint(sys.path)
    print("--- End Path Diagnostics ---\n")

    # Determine which engine factories to load
    worker_factories = {}
    
    if config['engines']['vnpy']['enabled']:
        worker_factories['vnpy'] = create_vnpy_worker
        print("✅ Vnpy engine enabled")
    
    if config['engines']['backtrader']['enabled']:
        try:
            from .adapters.backtrader_adapter import create_backtrader_worker
            worker_factories['backtrader'] = create_backtrader_worker
            print("✅ Backtrader engine enabled")
        except ImportError:
            print("⚠️  Backtrader adapter not available")
    
    if not worker_factories:
        print("❌ No engines enabled in configuration")
        return 1
    
    # Create orchestrator
    orchestrator = MultiStrategyOrchestrator(
        worker_factories=worker_factories,
        mongo_uri=config['mongo_uri'],
        mongo_db=config['mongo_db'],
        config_collection=config['config_collection'],
        user_id=args.user_id,
        auto_reload_interval=config['auto_reload_interval'],
    )
    
    # Create lifecycle manager if enabled
    lifecycle_mgr = None
    if config.get('enable_lifecycle', True):
        lc_config = config.get('lifecycle', {})
        lifecycle_mgr = LifecycleManager(
            auto_start=lc_config.get('auto_start', True),
            auto_stop=lc_config.get('auto_stop', True),
        )
        print("✅ Lifecycle management enabled")
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        print("\n⏹️  Stopping all workers...")
        if lifecycle_mgr:
            lifecycle_mgr.stop()
        orchestrator.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Load configurations and start workers
        print("\n📊 Loading strategy configurations...")
        orchestrator.start_all()
        
        print(f"\n✅ Started {len(orchestrator.workers)} workers")
        
        # Register with lifecycle manager
        if lifecycle_mgr:
            print("\n🔄 Registering workers with lifecycle manager...")
            for key, worker in orchestrator.workers.items():
                config_obj = orchestrator.configurations.get(key)
                if config_obj:
                    # Get appropriate factory
                    factory = worker_factories.get(config_obj.engine)
                    if factory:
                        worker_config = {
                            'symbol': config_obj.symbol,
                            'strategy_key': config_obj.strategy_key,
                            'params': config_obj.params,
                            'user_id': config_obj.user_id,
                        }
                        
                        # Add engine-specific fields
                        if config_obj.engine == 'vnpy':
                            worker_config['engine_class_path'] = config_obj.engine_class
                        
                        lifecycle_mgr.add_worker(worker, factory=factory, config=worker_config)
            
            lifecycle_mgr.start()
            print(f"✅ Registered {len(orchestrator.workers)} workers")
        
        print("\n" + "=" * 80)
        print("✅ Strategy Manager running")
        if lifecycle_mgr:
            print("   • Lifecycle: Auto stop at 15:05, auto start at 09:25")
        print(f"   • Config reload: Every {config['auto_reload_interval']}s")
        print("   • Press Ctrl+C to stop")
        print("=" * 80 + "\n")
        
        # Keep running
        while True:
            time.sleep(10)
            
            # Print status periodically
            if args.verbose and int(time.time()) % 300 == 0:
                status = orchestrator.get_status()
                print(f"\n📊 Workers: {status['total_workers']} | Configs: {status['active_configs']}")
                
                if lifecycle_mgr:
                    lc_status = lifecycle_mgr.get_status()
                    print(f"   Active: {lc_status['active_workers']}/{lc_status['total_workers']}")
    
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if lifecycle_mgr:
            lifecycle_mgr.stop()
        orchestrator.stop_all()
        print("\n✅ Shutdown complete")
    
    return 0


def cmd_status(args):
    """Show status of running strategies."""
    print("Strategy Manager - Status")
    print("=" * 80)
    # TODO: Implement status checking (could use PID file or REST API)
    print("Status checking not yet implemented")
    print("Use 'ps aux | grep strategy_manager' for now")
    return 0


def cmd_stop(args):
    """Stop running strategies."""
    print("Strategy Manager - Stop")
    print("=" * 80)
    # TODO: Implement graceful stop (could use PID file or signal)
    print("Stop command not yet implemented")
    print("Use 'kill -TERM <PID>' for now")
    return 0


def cmd_config(args):
    """Show configuration sources and loaded values."""
    from .config_loader import print_config_sources
    
    print_config_sources()
    
    if args.show:
        config = load_config_with_env()
        print("\nLoaded Configuration Values:")
        print("=" * 80)
        print(json.dumps(config, indent=2, default=str))
        print("=" * 80)
    
    return 0


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Strategy Manager - Engine-agnostic trading orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with default config
  python -m strategy_manager.cli start
  
  # Start with custom config
  python -m strategy_manager.cli start --config prod.json
  
  # Start for specific user
  python -m strategy_manager.cli start --user-id user123
  
  # Check status
  python -m strategy_manager.cli status
        """
    )
    
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start strategy manager")
    start_parser.add_argument("--config", help="Path to config JSON file")
    start_parser.add_argument("--user-id", help="Filter strategies by user ID")
    start_parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show status")
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop running strategies")
    stop_parser.add_argument("--graceful", action="store_true", help="Graceful shutdown")
    
    # Config command (new)
    config_parser = subparsers.add_parser("config", help="Show configuration sources")
    config_parser.add_argument("--show", action="store_true", help="Show loaded config values")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Execute command
    if args.command == "start":
        return cmd_start(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "stop":
        return cmd_stop(args)
    elif args.command == "config":
        return cmd_config(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
