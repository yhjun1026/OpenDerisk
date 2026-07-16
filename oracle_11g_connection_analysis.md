# Oracle 11g 连接问题分析

## 问题现象

新版本资源协议连接 Oracle 11g 报错：
```
DPY-3010: connections to this database server version are not supported by python-oracledb in thin mode
```

## 根本原因

### 旧版本逻辑 (datasource.py:133-138)
```python
def __init__(self, name: str, db_name: Optional[str] = None, db_id=None, **kwargs):
    # ✅ 立即建立连接
    conn = CFG.local_db_manager.get_connector(db_name, db_id=db_id)
    # ✅ thick mode 在这里自动初始化
    super().__init__(name, connector=conn, db_name=db_name, **kwargs)
```

### 新版本逻辑 (db/capability.py:203-232)
```python
@classmethod
def from_config(cls, value: dict, system_app: Any = None) -> "DBCapability":
    # ❌ 只保存配置,不建立连接
    return cls(db_name=db_name, db_id=db_id, db_type=db_type, dialect=dialect)

async def prepare(self) -> None:
    # ⚠️ 延迟到 prepare() 时才建立连接
    self._connector = await asyncio.to_thread(self._build_connector)
```

### 问题流程

1. 旧版本：创建资源时立即调用 `get_connector()`
   - `get_connector()` → `from_uri_db()` → **auto_detect thick mode** → ✅ 成功

2. 新版本：延迟到 `prepare()` 时才调用 `get_connector()`
   - 如果在 `prepare()` 之前没有手动初始化 thick mode → ❌ 失败

## 为什么不能使用旧版本的逻辑？

### 可以！但违反 RFC-005 设计原则

新版本**完全可以**在 `from_config()` 中就建立连接，技术上没有障碍。但是这会违反 RFC-005 的架构设计：

### RFC-005 的设计目标

| 原则 | 旧版本 | 新版本 |
|------|--------|--------|
| **配置薄、实现厚** | ❌ 配置时就建立连接(重) | ✅ 配置只存参数,实现时才建连接 |
| **生命周期可治理** | ❌ 连接时机不可控 | ✅ prepare/release 可控 |
| **声明面纯函数** | ❌ `__init__` 有I/O | ✅ `from_config` 无I/O |
| **缓存友好** | ❌ 每次创建都建连接 | ✅ 可缓存 prepare 结果 |

### RFC-005 Section 3.3 明确规定

```python
class ResourceProtocol(ABC):
    @classmethod
    @abstractmethod
    def declare(cls, config: "ResourceConfig") -> List[Contribution]:
        """声明面【纯函数,无 I/O】
        需外部数据(schema)时,Contribution.content 带 data_requirement,
        由执行投影预取后回填,再格式化。"""
```

## 解决方案

### 方案 1: 在 prepare() 中检测并初始化 thick mode (推荐)

```python
# db/capability.py

async def prepare(self) -> None:
    """建 live connector,自动处理 Oracle thick mode"""
    if self._connector is not None:
        self._status = ExecutorStatus.READY
        return
    
    # ✅ 在建立连接前检测并初始化 thick mode
    if self._db_type == "oracle":
        await asyncio.to_thread(self._ensure_oracle_thick_mode)
    
    self._connector = await asyncio.to_thread(self._build_connector)
    # ...

def _ensure_oracle_thick_mode(self):
    """确保 Oracle thick mode 已初始化"""
    try:
        import oracledb
        # 检查是否已初始化
        if not hasattr(oracledb, '_thick_mode_initialized'):
            # 自动检测并初始化 thick mode
            oracledb.init_oracle_client()
            oracledb._thick_mode_initialized = True
    except Exception as e:
        logger.warning(f"[db-capability] Oracle thick mode init failed: {e}")
```

### 方案 2: 在 get_connector 中处理 (已部分实现)

`local_db_manager.get_connector()` 内部已经有 auto_detect 逻辑，问题在于：
- 旧版本：立即调用，thick mode 及时初始化
- 新版本：延迟调用，但如果 thick mode 未初始化就会失败

**修复**: 确保 `get_connector()` 每次都检查 thick mode

### 方案 3: 启动时预初始化 (不推荐)

在应用启动时初始化 thick mode，但这样违反了"按需初始化"的原则。

## 推荐做法

**采用方案 1**，在 `DBCapability.prepare()` 中添加 Oracle thick mode 自动检测逻辑，这样：

1. ✅ 保持 RFC-005 的架构原则不变
2. ✅ 兼容 Oracle 11g 的 thick mode 要求
3. ✅ 其他数据库类型不受影响
4. ✅ 延迟初始化的优势得以保留

## 相关文件

- `packages/derisk-serve/src/derisk_serve/agent/capabilities/db/capability.py:203-232` - prepare() 方法
- `packages/derisk-serve/src/derisk_serve/agent/resource/datasource.py:133-138` - 旧版本逻辑
- `docs/rfc/RFC-005-resource-protocol.md` - RFC 设计文档