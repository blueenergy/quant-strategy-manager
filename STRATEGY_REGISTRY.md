# Strategy Registry - 快速参考

## 🎯 问题背景

**之前的做法（不推荐）**：
```javascript
// 数据库中需要存储实现细节
{
  "engine": "vnpy",
  "strategy_key": "hidden_dragon",
  "engine_class": "scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine"  // ❌ 实现细节暴露
}
```

**问题**：
- `engine_class` 是内部实现细节，不应暴露给用户/数据库
- UI 保存时需要知道复杂的类路径
- 修改引擎类路径需要更新所有数据库记录

## ✅ 新的解决方案

**现在的做法（推荐）**：
```javascript
// 数据库只需要存储用户关心的信息
{
  "engine": "vnpy",
  "strategy_key": "hidden_dragon"  // ✅ 只需要策略标识符
  // engine_class 字段不需要了！
}
```

**优势**：
- 数据库不包含实现细节
- UI 只需要提供策略选择（如下拉菜单）
- 修改引擎类只需改代码，不用碰数据库

## 📋 支持的策略

当前注册的策略（在 `strategy_registry.py` 中）：

| strategy_key | 说明 | 引擎类 |
|--------------|------|--------|
| `hidden_dragon` | 潜龙出海 | SingleStreamRealTimeEngine |
| `turtle` | 海龟交易 | TurtleRealTimeEngine |
| `single_yang` | 单阳不破 | SingleYangRealTimeEngine |
| `grid` | 网格交易 | GridRealTimeEngine |

## 🔧 如何添加新策略

### 步骤 1: 在注册表中添加映射

编辑 `src/strategy_manager/strategy_registry.py`：

```python
class StrategyRegistry:
    _VNPY_STRATEGIES: Dict[str, str] = {
        "hidden_dragon": "scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine",
        "turtle": "scripts.single_stream_turtle.SingleStreamRealTimeEngine",
        
        # 添加新策略
        "my_new_strategy": "scripts.my_new_strategy.MyStrategyEngine",  # ← 这里
    }
```

### 步骤 2: 数据库中使用新策略

```javascript
// 直接使用新的 strategy_key
{
  "engine": "vnpy",
  "strategy_key": "my_new_strategy",  // ✅ 就这么简单
  "params": { /* ... */ }
}
```

### 步骤 3: UI 下拉菜单更新

前端只需要提供策略选项：

```javascript
const strategies = [
  { key: 'hidden_dragon', label: '潜龙出海' },
  { key: 'turtle', label: '海龟交易' },
  { key: 'my_new_strategy', label: '我的新策略' },  // ← 添加选项
]
```

## 🔄 数据库迁移

如果你的数据库中已有 `engine_class` 字段，运行迁移脚本清理：

```bash
# 查看会删除哪些字段（不修改数据库）
python scripts/migrate_remove_engine_class.py --dry-run

# 实际执行迁移
python scripts/migrate_remove_engine_class.py
```

## 📝 代码示例

### 手动查询策略引擎类

```python
from strategy_manager.strategy_registry import get_engine_class_for_strategy

# 查询策略对应的引擎类
engine_class = get_engine_class_for_strategy('hidden_dragon', engine='vnpy')
print(engine_class)
# 输出: scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine
```

### 检查策略是否有效

```python
from strategy_manager.strategy_registry import StrategyRegistry

if StrategyRegistry.is_valid_strategy('hidden_dragon'):
    print("✓ Valid strategy")
else:
    print("✗ Unknown strategy")
```

### 列出所有策略

```python
from strategy_manager.strategy_registry import StrategyRegistry

strategies = StrategyRegistry.list_vnpy_strategies()
for key, engine_class in strategies.items():
    print(f"{key} → {engine_class}")
```

## 🎨 UI 集成示例

### Vue.js 组件

```vue
<template>
  <el-form-item label="策略类型">
    <el-select v-model="form.strategy_key">
      <el-option
        v-for="strategy in strategies"
        :key="strategy.key"
        :label="strategy.label"
        :value="strategy.key"
      />
    </el-select>
  </el-form-item>
</template>

<script>
export default {
  data() {
    return {
      form: {
        engine: 'vnpy',
        strategy_key: '',  // ← 只需要这两个字段
        params: {}
      },
      strategies: [
        { key: 'hidden_dragon', label: '潜龙出海策略' },
        { key: 'turtle', label: '海龟交易策略' },
        { key: 'single_yang', label: '单阳不破策略' },
        { key: 'grid', label: '网格交易策略' },
      ]
    }
  },
  methods: {
    async saveStrategy() {
      // 保存到数据库 - 不需要 engine_class！
      await axios.post('/api/strategies', {
        engine: this.form.engine,
        strategy_key: this.form.strategy_key,
        params: this.form.params
      })
    }
  }
}
</script>
```

## ⚙️ 系统内部处理流程

```
用户保存策略
  ↓
数据库: { engine: "vnpy", strategy_key: "hidden_dragon" }
  ↓
Orchestrator 读取配置
  ↓
调用: get_engine_class_for_strategy("hidden_dragon", "vnpy")
  ↓
StrategyRegistry 查找映射
  ↓
返回: "scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine"
  ↓
VnpyWorkerAdapter 动态导入引擎类
  ↓
启动策略
```

## 🔒 向后兼容

系统仍然支持旧格式（包含 `engine_class` 字段）：

```javascript
// 旧格式（仍然有效，但不推荐）
{
  "engine": "vnpy",
  "strategy_key": "hidden_dragon",
  "engine_class": "scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine"
}
```

处理逻辑：
1. 如果数据库中有 `engine_class`，优先使用
2. 如果没有 `engine_class`，从注册表查找
3. 都找不到则报错

## 📚 相关文件

- `src/strategy_manager/strategy_registry.py` - 策略注册表
- `src/strategy_manager/core/multi_strategy_orchestrator.py` - 自动解析逻辑
- `scripts/migrate_remove_engine_class.py` - 数据库迁移脚本
- `README.md` - 完整文档
