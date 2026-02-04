# Flexible Logging Configuration Guide

本文档说明如何配置日志系统，支持本地文件、ELK、Loki、Graylog 等多个后端。

## 快速开始（默认配置）

默认使用本地文件存储日志，无需任何额外配置：

```bash
# 默认写入到 vnpy-live-trading/logs/workers/ 目录
python -m strategy_manager.worker
```

## 配置方式

### 1. 环境变量配置（推荐）

设置 `LOG_BACKEND` 环境变量来选择日志后端：

```bash
# 本地文件（默认）
export LOG_BACKEND=file
export LOG_FILE_PATH=/home/user/logs/trading.log
export LOG_FILE_MAX_BYTES=10485760  # 10MB
export LOG_FILE_BACKUP_COUNT=5

# 或 ELK
export LOG_BACKEND=elk
export LOG_ELK_HOST=elasticsearch.example.com
export LOG_ELK_PORT=9200
export LOG_ELK_INDEX=trading-logs

# 或 Loki
export LOG_BACKEND=loki
export LOG_LOKI_HOST=loki.example.com
export LOG_LOKI_PORT=3100

# 日志级别
export LOG_LEVEL=INFO
```

### 2. .env 文件配置

创建 `.env` 文件在项目根目录：

```bash
# .env
LOG_BACKEND=file
LOG_FILE_PATH=/var/log/trading/worker.log
LOG_LEVEL=INFO
```

## 支持的后端

### 1. **本地文件（file）** - 默认

最简单的方案，日志写入本地文件系统：

```bash
LOG_BACKEND=file
LOG_FILE_PATH=/var/log/trading/worker.log
LOG_FILE_MAX_BYTES=10485760          # 文件大小限制（字节）
LOG_FILE_BACKUP_COUNT=5               # 备份文件数
```

**优点：**
- 无外部依赖
- 零配置
- 性能最好
- 占用磁盘空间

**场景：**
- 开发测试
- 小规模部署（<10 workers）
- 本地调试

---

### 2. **Elasticsearch/ELK（elk）**

完整的日志收集、存储和分析系统：

```bash
LOG_BACKEND=elk
LOG_ELK_HOST=elasticsearch.example.com
LOG_ELK_PORT=9200
LOG_ELK_INDEX=trading-logs
```

**安装依赖：**
```bash
pip install elasticsearch
```

**Docker 快速启动：**
```bash
# Elasticsearch
docker run -d -p 9200:9200 \
  -e "discovery.type=single-node" \
  docker.elastic.co/elasticsearch/elasticsearch:7.14.0

# Kibana（可视化）
docker run -d -p 5601:5601 \
  docker.elastic.co/kibana/kibana:7.14.0
```

访问 Kibana: http://localhost:5601

**优点：**
- 强大的搜索和过滤能力
- 完整的日志分析
- 可视化和告警
- 支持大规模日志（TB级）

**场景：**
- 生产环境
- 大规模部署（100+ workers）
- 需要深度分析

**成本：** 中等（服务器成本）

---

### 3. **Grafana Loki（loki）**

轻量级的日志聚合系统，与 Grafana 集成：

```bash
LOG_BACKEND=loki
LOG_LOKI_HOST=loki.example.com
LOG_LOKI_PORT=3100
```

**安装依赖：**
```bash
pip install python-json-logger
```

**Docker 快速启动：**
```bash
# Loki
docker run -d -p 3100:3100 \
  grafana/loki:latest

# Grafana
docker run -d -p 3000:3000 \
  grafana/grafana:latest
```

访问 Grafana: http://localhost:3000 (admin/admin)

**优点：**
- 轻量级（内存占用少）
- 成本低
- 与 Prometheus 生态兼容
- 易于部署

**场景：**
- 中等规模部署（50-500 workers）
- 已有 Prometheus 监控
- 资源受限环境

**成本：** 低

---

### 4. **Graylog（graylog）**

功能完整的日志管理平台：

```bash
LOG_BACKEND=graylog
LOG_GRAYLOG_HOST=graylog.example.com
LOG_GRAYLOG_PORT=12201
```

**安装依赖：**
```bash
pip install graypy
```

**Docker 快速启动：**
```bash
docker run -d \
  -p 9000:9000 \
  -p 1514:1514/udp \
  graylog/graylog:4.0
```

访问 Graylog: http://localhost:9000 (admin/admin)

**优点：**
- 开源免费
- 功能全面
- 易于集群部署
- 内置告警和分析

**场景：**
- 生产环境
- 中等规模（50-200 workers）
- 需要告警和分析

**成本：** 低（自建）

---

### 5. **控制台（console）** - 仅用于测试

日志输出到标准输出，仅用于开发调试：

```bash
LOG_BACKEND=console
LOG_LEVEL=DEBUG
```

---

## 生产环境建议

### 场景1：小规模（<10 workers）
```bash
# 使用本地文件，配合日志轮转
LOG_BACKEND=file
LOG_FILE_PATH=/var/log/trading/worker.log
LOG_FILE_MAX_BYTES=104857600        # 100MB
LOG_FILE_BACKUP_COUNT=10            # 保留10个备份
LOG_LEVEL=INFO
```

### 场景2：中等规模（50-500 workers）
```bash
# 使用 Loki，轻量级且成本低
LOG_BACKEND=loki
LOG_LOKI_HOST=loki.internal.example.com
LOG_LOKI_PORT=3100
LOG_LEVEL=INFO
```

### 场景3：大规模（1000+ workers）
```bash
# 使用 ELK Stack，功能全面
LOG_BACKEND=elk
LOG_ELK_HOST=elasticsearch.internal.example.com
LOG_ELK_PORT=9200
LOG_ELK_INDEX=trading-logs-{date}
LOG_LEVEL=INFO
```

## 故障排除

### 日志未出现在远程系统

1. **检查配置：**
   ```bash
   python -c "from strategy_manager.log_config import LogConfig; print(LogConfig.get_config())"
   ```

2. **检查连接：**
   ```bash
   # ELK
   curl http://elasticsearch:9200/_health
   
   # Loki
   curl http://loki:3100/loki/api/v1/query
   
   # Graylog
   telnet graylog 12201
   ```

3. **启用 DEBUG 日志：**
   ```bash
   export LOG_LEVEL=DEBUG
   ```

### 依赖包安装失败

确保安装了正确的包：

```bash
# ELK
pip install elasticsearch>=7.0,<8.0

# Loki
pip install python-json-logger

# Graylog
pip install graypy
```

## 监控日志

### 使用 grep 查看本地文件
```bash
tail -f /var/log/trading/worker.log | grep "ERROR\|WARNING"
```

### 使用 Kibana 查看 ELK 日志
1. 打开 http://localhost:5601
2. 创建 Index Pattern: `trading-logs*`
3. 使用 Discover 查看日志

### 使用 Grafana 查看 Loki 日志
1. 打开 http://localhost:3000
2. 添加 Loki 数据源
3. 在 Explore 中查询日志

## 常见问题

**Q: 本地文件日志会占用很多磁盘空间吗？**

A: 会。建议：
- 定期清理旧日志
- 使用 logrotate 自动管理
- 或迁移到远程系统

**Q: 远程日志系统会影响交易性能吗？**

A: 可能会。建议：
- 使用异步日志处理
- 在单独的线程发送日志
- 使用 UDP（Graylog）而非 HTTP

**Q: 如何在线切换日志后端？**

A: 通过修改环境变量后重启 worker：
```bash
export LOG_BACKEND=elk
# 重启 worker
```

**Q: 能否同时输出到多个后端？**

A: 目前不支持。可以修改 `log_config.py` 添加此功能。

## 更多帮助

查看示例配置：
```bash
cat .env.logging.example
```

查看日志配置源码：
```bash
cat src/strategy_manager/log_config.py
```
