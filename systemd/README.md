# Systemd 服务配置

## 📋 服务文件

- `worker-api.service` - Worker API Server (port 5000)

## 🚀 安装步骤

### 1. 复制服务文件

```bash
# 复制到系统 systemd 目录
sudo cp ~/trading/quant-strategy-manager/systemd/worker-api.service /etc/systemd/system/

# 或者创建软链接（推荐，便于更新）
sudo ln -sf ~/trading/quant-strategy-manager/systemd/worker-api.service /etc/systemd/system/
```

### 2. 重新加载 systemd

```bash
sudo systemctl daemon-reload
```

### 3. 启用服务（开机自启动）

```bash
sudo systemctl enable worker-api
```

### 4. 启动服务

```bash
sudo systemctl start worker-api
```

## 📊 服务管理

### 查看状态

```bash
# 查看服务状态
sudo systemctl status worker-api

# 查看是否启用
sudo systemctl is-enabled worker-api

# 查看是否运行
sudo systemctl is-active worker-api
```

### 控制服务

```bash
# 启动
sudo systemctl start worker-api

# 停止
sudo systemctl stop worker-api

# 重启
sudo systemctl restart worker-api

# 重新加载配置（不中断服务）
sudo systemctl reload worker-api
```

### 查看日志

```bash
# 查看所有日志
sudo journalctl -u worker-api

# 实时查看日志（类似 tail -f）
sudo journalctl -u worker-api -f

# 查看最近 100 行
sudo journalctl -u worker-api -n 100

# 查看今天的日志
sudo journalctl -u worker-api --since today

# 查看最近 1 小时的日志
sudo journalctl -u worker-api --since "1 hour ago"

# 只看错误日志
sudo journalctl -u worker-api -p err
```

## 🔧 配置说明

### 环境变量

在服务文件中修改 `Environment=` 行：

```ini
# API 端口
Environment="API_PORT=5000"

# MongoDB 配置
Environment="MONGO_URI=mongodb://localhost:27017"
Environment="MONGO_DB=finance"

# 禁用 MongoDB 实时日志（提升性能）
Environment="ENABLE_MONGO_LOGS=false"
```

### 用户和组

修改服务运行的用户（默认 shuyolin）：

```ini
User=your_username
Group=your_group
```

### 工作目录

确保路径正确：

```ini
WorkingDirectory=/home/shuyolin/trading/quant-strategy-manager
```

### Python 环境

确保使用 vnpy 虚拟环境：

```ini
Environment="PATH=/home/shuyolin/trading/vnpy-live-trading/.venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/home/shuyolin/trading/vnpy-live-trading/.venv/bin/python api_server.py
```

## 🔍 故障排查

### 服务无法启动

```bash
# 1. 查看详细日志
sudo journalctl -u worker-api -n 50 --no-pager

# 2. 检查服务文件语法
sudo systemd-analyze verify /etc/systemd/system/worker-api.service

# 3. 测试手动运行
cd ~/trading/quant-strategy-manager
source ~/trading/vnpy-live-trading/.venv/bin/activate
python api_server.py
```

### 权限问题

```bash
# 检查文件权限
ls -la ~/trading/quant-strategy-manager/api_server.py

# 检查日志目录权限
ls -la ~/trading/vnpy-live-trading/logs/workers/

# 创建日志目录（如果不存在）
mkdir -p ~/trading/vnpy-live-trading/logs/workers/
```

### 端口被占用

```bash
# 检查端口占用
sudo ss -tlnp | grep :5000
sudo lsof -i :5000

# 修改端口（在服务文件中添加）
Environment="API_PORT=5001"
```

### 依赖服务未启动

```bash
# 检查 MongoDB
sudo systemctl status mongodb

# 检查 Redis
sudo systemctl status redis

# 如果不需要这些依赖，修改服务文件：
# After=network.target
# Wants=
```

## 📈 性能监控

### 资源使用

```bash
# 查看 CPU 和内存使用
systemctl status worker-api

# 详细资源信息
systemd-cgtop

# 查看服务的资源限制
systemctl show worker-api | grep -E "LimitNOFILE|LimitNPROC|CPUQuota|MemoryLimit"
```

### 日志大小管理

```bash
# 查看日志占用空间
sudo journalctl --disk-usage

# 清理旧日志（保留最近 7 天）
sudo journalctl --vacuum-time=7d

# 限制日志大小（保留最大 500MB）
sudo journalctl --vacuum-size=500M
```

## 🔒 安全建议

1. **最小权限原则**：使用专用用户运行服务
   ```bash
   # 创建专用用户
   sudo useradd -r -s /bin/false worker-api
   
   # 修改服务文件
   User=worker-api
   Group=worker-api
   ```

2. **防火墙配置**：只允许必要的端口
   ```bash
   # 只允许本地访问
   sudo firewall-cmd --add-rich-rule='rule family="ipv4" source address="127.0.0.1" port port="5000" protocol="tcp" accept' --permanent
   sudo firewall-cmd --reload
   ```

3. **日志轮转**：防止日志占满磁盘
   ```bash
   # 编辑 /etc/systemd/journald.conf
   SystemMaxUse=1G
   RuntimeMaxUse=100M
   ```

## 🔄 更新服务

修改服务文件后：

```bash
# 1. 重新加载 systemd 配置
sudo systemctl daemon-reload

# 2. 重启服务
sudo systemctl restart worker-api

# 3. 验证
sudo systemctl status worker-api
```

## 📚 相关命令速查

```bash
# 一键查看服务状态和最新日志
sudo systemctl status worker-api && sudo journalctl -u worker-api -n 20

# 监控服务（自动刷新）
watch -n 2 'sudo systemctl status worker-api'

# 导出日志到文件
sudo journalctl -u worker-api --since "1 day ago" > ~/worker-api.log

# 检查服务是否在运行并监听端口
sudo systemctl is-active worker-api && sudo ss -tlnp | grep :5000
```
