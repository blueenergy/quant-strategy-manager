#!/usr/bin/env python3
"""
测试 WebSocket 日志流功能

此示例展示如何：
1. 启动带日志流的 Worker
2. 获取 WebSocket URL
3. 在浏览器中查看实时日志

使用方法:
    python examples/test_log_streaming.py
    
然后在浏览器中打开:
    file:///.../quant-strategy-manager/examples/log_viewer.html
"""

import time
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(project_root))

from strategy_manager.log_stream_server import LogStreamServer
from strategy_manager.log_handlers import WebSocketLogHandler


def test_log_streaming():
    """测试基本的日志流功能"""
    print("=" * 80)
    print("WebSocket 日志流测试")
    print("=" * 80)
    
    # 1. 创建日志流服务器（动态端口）
    log_server = LogStreamServer(host="0.0.0.0", port=0)
    log_server.start()
    
    host, port = log_server.get_address()
    ws_url = f"ws://{host}:{port}"
    
    print(f"\n✅ 日志流服务器已启动")
    print(f"   WebSocket URL: {ws_url}")
    print(f"\n请在浏览器中打开:")
    print(f"   file://{Path(__file__).parent.absolute()}/log_viewer.html")
    print(f"\n然后输入 WebSocket URL: {ws_url}")
    print(f"\n按 Ctrl+C 停止...")
    print("=" * 80 + "\n")
    
    # 2. 创建 Logger 并添加 WebSocket Handler
    logger = logging.getLogger("TestWorker")
    logger.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)
    
    # WebSocket handler
    ws_handler = WebSocketLogHandler(log_server)
    ws_handler.setFormatter(console_fmt)
    logger.addHandler(ws_handler)
    
    # 3. 模拟策略运行，产生日志
    try:
        counter = 0
        while True:
            counter += 1
            
            # 每秒产生不同级别的日志
            if counter % 10 == 0:
                logger.warning(f"⚠️  Warning: High volatility detected (counter={counter})")
            elif counter % 5 == 0:
                logger.info(f"📊 Position updated: +100 shares at $50.25")
            elif counter % 3 == 0:
                logger.debug(f"🔍 Debug: Processing bar #{counter}")
            else:
                logger.info(f"✅ Bar processed: #{counter}")
            
            # 模拟错误
            if counter == 15:
                logger.error("❌ Error: Failed to submit order - insufficient margin")
            
            if counter == 25:
                logger.critical("🚨 Critical: Risk limit exceeded! Stopping all trading.")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 停止测试...")
        log_server.stop()
        print("✅ 日志流服务器已停止")


def test_multi_worker_simulation():
    """测试多个 Worker 的日志流（模拟实际场景）"""
    print("=" * 80)
    print("多 Worker 日志流测试")
    print("=" * 80)
    
    workers = []
    
    # 创建 3 个模拟 Worker
    symbols = ["002050.SZ", "600132.SH", "000002.SZ"]
    
    for symbol in symbols:
        # 每个 Worker 一个独立的日志服务器
        log_server = LogStreamServer(host="0.0.0.0", port=0)
        log_server.start()
        
        host, port = log_server.get_address()
        ws_url = f"ws://{host}:{port}"
        
        # 创建 Logger
        logger = logging.getLogger(f"Worker[{symbol}]")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        
        # 添加 handlers
        console_handler = logging.StreamHandler()
        console_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        console_handler.setFormatter(console_fmt)
        logger.addHandler(console_handler)
        
        ws_handler = WebSocketLogHandler(log_server)
        ws_handler.setFormatter(console_fmt)
        logger.addHandler(ws_handler)
        
        workers.append({
            'symbol': symbol,
            'logger': logger,
            'log_server': log_server,
            'ws_url': ws_url
        })
        
        print(f"✅ Worker[{symbol}] - {ws_url}")
    
    print(f"\n请在浏览器中打开多个标签页:")
    print(f"   file://{Path(__file__).parent.absolute()}/log_viewer.html")
    print(f"\n分别连接到不同的 Worker URL")
    print(f"\n按 Ctrl+C 停止...")
    print("=" * 80 + "\n")
    
    try:
        counter = 0
        while True:
            counter += 1
            
            # 每个 Worker 随机产生日志
            import random
            for worker in workers:
                if random.random() > 0.5:
                    symbol = worker['symbol']
                    logger = worker['logger']
                    
                    log_types = [
                        (logging.INFO, f"✅ [{symbol}] Bar #{counter} processed"),
                        (logging.INFO, f"📊 [{symbol}] Position: +500 shares"),
                        (logging.WARNING, f"⚠️  [{symbol}] Stop loss triggered"),
                        (logging.DEBUG, f"🔍 [{symbol}] Market depth updated"),
                    ]
                    
                    level, msg = random.choice(log_types)
                    logger.log(level, msg)
            
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n\n🛑 停止测试...")
        for worker in workers:
            worker['log_server'].stop()
        print("✅ 所有日志流服务器已停止")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "multi":
        test_multi_worker_simulation()
    else:
        test_log_streaming()
