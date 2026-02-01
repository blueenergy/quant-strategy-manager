"""Example: Using quant-strategy-manager with vnpy-live-trading.

This shows how to use the independent strategy manager library
to orchestrate vnpy strategies with lifecycle management.
"""

import signal
import sys
import time
import logging

from strategy_manager.core import MultiStrategyOrchestrator, LifecycleManager
from strategy_manager.adapters.vnpy_adapter import create_vnpy_worker


def main():
    """Run vnpy strategies with automated lifecycle management."""
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    
    print("=" * 80)
    print("Vnpy Strategy Manager - Live Trading")
    print("=" * 80)
    
    # Create orchestrator with vnpy support
    orchestrator = MultiStrategyOrchestrator(
        worker_factories={
            "vnpy": create_vnpy_worker,
        },
        mongo_uri="mongodb://localhost:27017",
        mongo_db="finance",
        config_collection="watchlist_strategies",
        auto_reload_interval=60,  # Reload config every 60s
    )
    
    # Create lifecycle manager for automatic start/stop
    lifecycle_mgr = LifecycleManager(
        auto_start=True,
        auto_stop=True,
        check_interval_sec=30,
    )
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        print("\n⏹️  Stopping all workers...")
        lifecycle_mgr.stop()
        orchestrator.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Load configurations and start workers
        print("\n📊 Loading strategy configurations from database...")
        orchestrator.start_all()
        
        print(f"\n✅ Started {len(orchestrator.workers)} workers")
        
        # Register workers with lifecycle manager
        print("\n🔄 Registering workers with lifecycle manager...")
        for key, worker in orchestrator.workers.items():
            config = orchestrator.configurations.get(key)
            if config:
                worker_config = {
                    'symbol': config.symbol,
                    'strategy_key': config.strategy_key,
                    'engine_class_path': config.engine_class,
                    'params': config.params,
                    'user_id': config.user_id,
                }
                lifecycle_mgr.add_worker(
                    worker,
                    factory=create_vnpy_worker,
                    config=worker_config
                )
        
        # Start lifecycle manager
        lifecycle_mgr.start()
        
        print("\n" + "=" * 80)
        print("✅ Vnpy strategy manager running")
        print("   • Lifecycle management: ENABLED")
        print("   • Auto stop at 15:05 (market close)")
        print("   • Auto start at 09:25 (next trading day)")
        print("   • Config hot reload: Every 60s")
        print("\nPress Ctrl+C to stop")
        print("=" * 80)
        
        # Keep running
        while True:
            time.sleep(10)
            
            # Print status every 5 minutes
            if int(time.time()) % 300 == 0:
                status = orchestrator.get_status()
                print(f"\n📊 Status: {status['total_workers']} workers running")
                
                lc_status = lifecycle_mgr.get_status()
                print(f"   Lifecycle: {lc_status['active_workers']}/{lc_status['total_workers']} active")
                print(f"   Trading time: {lc_status['is_trading_time']}")
    
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        lifecycle_mgr.stop()
        orchestrator.stop_all()
        print("\n✅ Shutdown complete")


if __name__ == "__main__":
    main()
