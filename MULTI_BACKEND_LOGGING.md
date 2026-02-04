# 多后端日志配置指南

## 核心特性：同时写多个后端

现在支持**同时写本地和远程**，既保证数据可靠性，也支持中央分析。

## 最常用场景

### 场景1：本地备份 + ELK分析（推荐生产环境）

```bash
# 既有本地备份，也上传到ELK做中央分析和监控
export LOG_BACKENDS=file,elk
export LOG_FILE_PATH=/var/log/trading/app.log
export LOG_ELK_HOST=elasticsearch.example.com
export LOG_ELK_PORT=9200
export LOG_ELK_INDEX=trading-logs
export LOG_ELK_USERNAME=elastic              # 生产环境需要认证
export LOG_ELK_PASSWORD=yourpassword
export LOG_ELK_USE_SSL=true                  # 生产环境使用HTTPS

# 启动worker（无需任何代码改动）
python -m strategy_manager.worker
```

**优点：**
- ✅ 本地备份，网络故障时日志不丢失
- ✅ ELK远程存储，支持复杂查询和分析
- ✅ 环境变量控制，零代码改动
- ✅ 失败自动降级（ELK故障时继续写本地）

### 场景2：本地 + Loki（轻量级方案）

```bash
export LOG_BACKENDS=file,loki
export LOG_FILE_PATH=/var/log/trading/app.log
export LOG_LOKI_HOST=loki.example.com
export LOG_LOKI_PORT=3100
```

**适用于：**
- 中等规模（50-500 workers）
- 需要即时可视化
- 资源有限

### 场景3：完整监控栈（file + elk + graylog）

```bash
export LOG_BACKENDS=file,elk,graylog
export LOG_FILE_PATH=/var/log/trading/app.log
export LOG_ELK_HOST=elasticsearch.example.com
export LOG_ELK_PORT=9200
export LOG_GRAYLOG_HOST=graylog.example.com
export LOG_GRAYLOG_PORT=12201
```

**优点：**
- 本地备份：网络故障保证日志不丢失
- ELK分析：复杂查询、聚合、统计
- Graylog告警：实时告警规则

## 配置语法

### 环境变量

```bash
# 后端列表（逗号分隔）
LOG_BACKENDS=file,elk,loki,graylog

# 后端特定配置
LOG_FILE_PATH=/var/log/app.log              # file
LOG_FILE_MAX_BYTES=10485760                 # file - 10MB
LOG_FILE_BACKUP_COUNT=5                     # file

LOG_ELK_HOST=elasticsearch.example.com      # elk
LOG_ELK_PORT=9200                           # elk
LOG_ELK_INDEX=trading-logs                  # elk
LOG_ELK_USERNAME=elastic                    # elk - 认证（可选）
LOG_ELK_PASSWORD=yourpassword               # elk - 认证（可选）
LOG_ELK_USE_SSL=true                        # elk - 使用HTTPS（可选，默认false）
LOG_ELK_VERIFY_CERTS=true                   # elk - 验证证书（可选，默认true）

LOG_LOKI_HOST=loki.example.com              # loki
LOG_LOKI_PORT=3100                          # loki

LOG_GRAYLOG_HOST=graylog.example.com        # graylog
LOG_GRAYLOG_PORT=12201                      # graylog

LOG_LEVEL=INFO                              # all backends
```

### .env 文件

```bash
# .env - 生产配置示例（含认证）
LOG_BACKENDS=file,elk
LOG_FILE_PATH=/var/log/trading/app.log
LOG_FILE_MAX_BYTES=10485760
LOG_FILE_BACKUP_COUNT=5
LOG_ELK_HOST=elasticsearch.example.com
LOG_ELK_PORT=9200
LOG_ELK_INDEX=trading-logs
LOG_ELK_USERNAME=elastic
LOG_ELK_PASSWORD=yourpassword
LOG_ELK_USE_SSL=true
LOG_LEVEL=INFO
```

## 快速启动

### 1. 默认本地文件（无需任何配置）

```bash
cd quant-strategy-manager
python -m strategy_manager.worker

# 日志自动写入: vnpy-live-trading/logs/workers/<user_id>_<strategy>_<symbol>.log
```

### 2. 启用ELK支持

```bash
# 1. 安装依赖
pip install elasticsearch

# 2a. 启动Elasticsearch（开发/测试 - 无认证）
docker run -d -p 9200:9200 \
  -e "discovery.type=single-node" \
  docker.elastic.co/elasticsearch/elasticsearch:7.14.0

# 2b. 启动Elasticsearch（生产 - 启用认证）
docker run -d -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=true" \
  -e "ELASTIC_PASSWORD=yourpassword" \
  docker.elastic.co/elasticsearch/elasticsearch:7.14.0

# 3. 配置环境变量（无认证）
export LOG_BACKENDS=file,elk
export LOG_FILE_PATH=/var/log/trading/app.log
export LOG_ELK_HOST=localhost
export LOG_ELK_PORT=9200

# 或配置（含认证）
export LOG_BACKENDS=file,elk
export LOG_FILE_PATH=/var/log/trading/app.log
export LOG_ELK_HOST=localhost
export LOG_ELK_PORT=9200
export LOG_ELK_USERNAME=elastic
export LOG_ELK_PASSWORD=yourpassword
export LOG_ELK_USE_SSL=false              # 本地开发可用HTTP

# 4. 启动worker
python -m strategy_manager.worker

# 5. 查看日志（无认证）
curl http://localhost:9200/trading-logs/_search?pretty

# 或查看日志（含认证）
curl -u elastic:yourpassword http://localhost:9200/trading-logs/_search?pretty
```

### 3. 启用Loki支持

```bash
# 1. 安装依赖
pip install python-json-logger

# 2. 启动Loki
docker run -d -p 3100:3100 grafana/loki:latest

# 3. 启动Grafana
docker run -d -p 3000:3000 grafana/grafana:latest

# 4. 配置环境变量
export LOG_BACKENDS=file,loki
export LOG_FILE_PATH=/var/log/trading/app.log
export LOG_LOKI_HOST=localhost
export LOG_LOKI_PORT=3100

# 5. 启动worker
python -m strategy_manager.worker

# 6. 在Grafana中添加Loki数据源 http://localhost:3100
```

### 4. 启用Graylog支持

```bash
# 1. 安装依赖
pip install graypy

# 2. 启动Graylog
docker run -d \
  -p 9000:9000 \
  -p 1514:1514/udp \
  -e GRAYLOG_PASSWORD_SECRET=somepasswordpepper \
  -e GRAYLOG_ROOT_PASSWORD_SHA2=8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918 \
  graylog/graylog:4.0

# 3. 配置环境变量
export LOG_BACKENDS=file,graylog
export LOG_FILE_PATH=/var/log/trading/app.log
export LOG_GRAYLOG_HOST=localhost
export LOG_GRAYLOG_PORT=12201

# 4. 启动worker
python -m strategy_manager.worker

# 5. 访问 http://localhost:9000 (admin/admin)
```

## 部署建议

| 规模 | 推荐方案 | 理由 |
|-----|--------|------|
| <10 workers | `LOG_BACKENDS=file` | 无外部依赖，本地备份足够 |
| 50-500 workers | `LOG_BACKENDS=file,loki` | 轻量级，支持复杂查询，Loki资源占用少 |
| 1000+ workers | `LOG_BACKENDS=file,elk` | ELK性能好，支持完整分析生态 |
| 需要告警 | `LOG_BACKENDS=file,elk,graylog` | 完整监控栈，支持实时告警 |

## 故障处理

### 如果ELK连接失败？

系统会自动降级到本地文件：

```
Warning: Some log backends failed to initialize: elk: Connection error to elasticsearch.example.com:9200
本地日志继续写入，数据不丢失
```

### 如果想临时禁用某个后端？

不需要删除代码，只需修改环境变量：

```bash
# 临时禁用ELK，只保留本地
export LOG_BACKENDS=file
# 重启worker即可
```

### 检查日志是否正确路由？

```bash
# 1. 本地文件日志
tail -f /var/log/trading/app.log

# 2. ELK查询
curl 'http://localhost:9200/trading-logs/_search?pretty&q=ERROR'

# 3. Loki查询
curl 'http://localhost:3100/loki/api/v1/query?query={job="trading"}'
```

## 性能考虑

- **本地文件**：<1ms延迟，几乎无CPU开销
- **ELK**：1-10ms延迟，批量发送优化
- **Loki**：1-5ms延迟，轻量级JSON编码
- **Graylog**：<1ms延迟（UDP异步）

多后端同时写入时，最慢的后端决定总延迟。建议：
- 优先用ELK做中央存储
- 用Loki做轻量级替代
- 用Graylog做告警补充

## 代码示例

初始化多后端日志：

```python
from strategy_manager.log_config import LogConfig

# 从环境变量自动配置
logger = LogConfig.setup_logger("my_worker")

# 代码无需改动，环境变量改变后自动应用
logger.info("Processing order...")
logger.error("Connection failed!")
```

环境变量改变后，日志自动流向配置的所有后端。

## 常见问题

**Q: 如果某个后端故障，其他后端会继续工作吗？**
A: 是的。系统为每个后端都做了错误处理，一个后端故障不会影响其他后端。

**Q: 能否动态改变后端配置而不重启？**
A: 目前需要重启worker，但我们计划支持信号处理热配置。

**Q: 多个worker同时写同一个本地文件是否安全？**
A: 安全。RotatingFileHandler使用锁机制保证线程安全。

**Q: 日志体积会很大吗？**
A: 本地文件使用RotatingFileHandler，自动轮转保留5个备份。ELK有索引生命周期管理。

**Q: 支持哪些日志格式？**
A: 本地文件用标准格式，ELK和Loki用JSON，Graylog用GELF。

## 下一步

1. 选择合适的后端组合
2. 设置环境变量
3. 启动相应的外部服务（如Elasticsearch）
4. 重启worker
5. 验证日志流向正确的目标

不需要修改任何业务代码！
