# quant-strategy-manager 架构重构说明

## 变更内容

### 问题
原先 `api_server.py` 运行在 `vnpy-live-trading/.venv` 环境中，导致：
- ❌ 策略模块（vnpy-live-trading）被污染了 API 相关依赖（fastapi, uvicorn, PyJWT）
- ❌ 职责不清晰：策略执行 vs API 服务混在一起
- ❌ 启动方式繁琐：先进 vnpy 目录激活环境，再切回 api 目录

### 解决方案
**架构分离**：两个模块各自管理依赖

```
vnpy-live-trading/          # 策略模块
├── .venv/                  # 纯粹的策略环境（vnpy, pymongo, ta-lib）
├── pyproject.toml          # ✨ 新增：让它可作为包安装
└── strategies/             # 策略代码

quant-strategy-manager/     # API 服务模块
├── .venv/                  # ✨ 新增：独立的 API 环境
├── init_env.sh             # ✨ 新增：一键初始化脚本
├── start_api_server.sh     # ✨ 修改：使用本地环境
└── api_server.py           # API 代码
```

## 使用方法

### 首次设置

```bash
cd ~/trading/quant-strategy-manager
bash init_env.sh
```

`init_env.sh` 会：
1. 创建 `.venv` 虚拟环境
2. 安装 API 依赖（fastapi, uvicorn, PyJWT, pymongo）
3. 以可编辑模式安装 vnpy-live-trading：`pip install -e ../vnpy-live-trading`

### 启动 API Server

```bash
cd ~/trading/quant-strategy-manager
bash start_api_server.sh
```

不再需要先进 vnpy 目录！

## 技术细节

### pip install -e 的作用

```bash
pip install -e ../vnpy-live-trading
```

- `-e`：可编辑模式（editable mode）
- 效果：在 `quant-strategy-manager/.venv` 中可以 `import strategy_manager`
- 优势：不复制代码，直接引用源文件，修改实时生效
- 原理：在 site-packages 中创建 `.pth` 文件指向源码目录

### pyproject.toml 配置

```toml
[tool.setuptools]
packages = ["strategy_manager", "adapters", "strategies"]
```

定义了哪些包可以被导入。

## 依赖隔离

**vnpy-live-trading/.venv**（策略环境）：
```
vnpy
vnpy-ctastrategy
pymongo
websockets
ta-lib
...
```

**quant-strategy-manager/.venv**（API 环境）：
```
fastapi
uvicorn
PyJWT
pymongo
python-dotenv
vnpy-live-trading (editable)  ← 通过 pip install -e 引入
```

## 优势

1. ✅ **职责清晰**：策略模块专注策略，API 模块专注服务
2. ✅ **依赖隔离**：各管各的包，不互相污染
3. ✅ **易于维护**：修改 vnpy 代码不需要重装，editable 模式实时生效
4. ✅ **启动简单**：直接在 quant-strategy-manager 目录启动，不用切换

## 迁移注意事项

- 原来的 `vnpy-live-trading/.venv` 保持不变，继续用于策略回测
- `quant-strategy-manager` 不再依赖 vnpy 环境
- 如果有其他脚本也用 vnpy 环境运行 API，需要相应修改
