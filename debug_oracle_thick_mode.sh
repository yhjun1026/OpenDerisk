#!/bin/bash
# 在服务器上运行：bash debug_oracle_thick_mode.sh

echo "=========================================="
echo "Oracle Thick Mode 详细诊断"
echo "=========================================="

# 1. 检查环境变量
echo -e "\n1. 检查环境变量"
echo "----------------------------------------"
echo "ORACLE_ENABLE_THICK_MODE: ${ORACLE_ENABLE_THICK_MODE:-未设置}"
echo "ORACLE_INSTANT_CLIENT_HOME: ${ORACLE_INSTANT_CLIENT_HOME:-未设置}"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH:-未设置}"

# 2. 检查 Instant Client 路径
echo -e "\n2. 检查 Instant Client 路径"
echo "----------------------------------------"
INSTANT_CLIENT_PATH="/opt/oracle/instantclient_11_2"
echo "检查路径: $INSTANT_CLIENT_PATH"

if [ -d "$INSTANT_CLIENT_PATH" ]; then
    echo "✅ 目录存在"
    echo -e "\n关键库文件:"
    ls -la "$INSTANT_CLIENT_PATH"/libclntsh.so* 2>/dev/null && echo "  ✅ libclntsh.so 存在" || echo "  ❌ libclntsh.so 不存在"
    ls -la "$INSTANT_CLIENT_PATH"/libociei.so* 2>/dev/null && echo "  ✅ libociei.so 存在" || echo "  ❌ libociei.so 不存在"
else
    echo "❌ 目录不存在"
    echo "搜索 instantclient..."
    find /opt/oracle -type d -name "*instantclient*" 2>/dev/null
fi

# 3. 检查系统依赖库
echo -e "\n3. 检查系统依赖库"
echo "----------------------------------------"
echo "检查 libaio:"
if ldconfig -p 2>/dev/null | grep -q libaio.so; then
    echo "✅ libaio 已安装"
    ldconfig -p | grep libaio
else
    echo "❌ libaio 未安装"
    echo "   安装命令: sudo apt-get install -y libaio1  (Ubuntu/Debian)"
    echo "   安装命令: sudo yum install -y libaio     (CentOS/RHEL)"
fi

echo -e "\n检查 libnsl:"
if ldconfig -p 2>/dev/null | grep -q libnsl.so; then
    echo "✅ libnsl 已安装"
    ldconfig -p | grep libnsl
else
    echo "⚠️  libnsl 未安装（可能需要）"
fi

# 4. 检查配置文件
echo -e "\n4. 检查配置文件"
echo "----------------------------------------"
CONFIG_FILE="$HOME/.derisk/derisk.json"
echo "配置文件: $CONFIG_FILE"

if [ -f "$CONFIG_FILE" ]; then
    echo "✅ 配置文件存在"
    echo -e "\n查看 datasource 配置:"
    cat "$CONFIG_FILE" | python3 -c "
import sys, json
try:
    config = json.load(sys.stdin)
    ds = config.get('datasource', {})
    print('oracle_enable_thick_mode:', ds.get('oracle_enable_thick_mode', '未设置'))
    print('oracle_instant_client_path:', ds.get('oracle_instant_client_path', '未设置'))
except Exception as e:
    print('解析失败:', e)
" 2>/dev/null || cat "$CONFIG_FILE"
else
    echo "❌ 配置文件不存在"
fi

# 5. 运行 Python 详细测试
echo -e "\n5. Python 详细测试"
echo "----------------------------------------"

cd "$(dirname "$0")"

uv run python << 'EOFPYTHON'
import sys
import os
import logging

# 启用详细日志
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, 'packages/derisk-core/src')
sys.path.insert(0, 'packages/derisk-serve/src')
sys.path.insert(0, 'packages/derisk-app/src')
sys.path.insert(0, 'packages/derisk-ext/src')

print("=" * 60)
print("测试 1: 配置读取")
print("=" * 60)

try:
    from derisk_core.config import ConfigManager

    config = ConfigManager.get()
    print(f"✅ ConfigManager 加载成功")

    if config and hasattr(config, 'datasource') and config.datasource:
        ds = config.datasource

        # 使用 model_dump 获取所有字段
        if hasattr(ds, 'model_dump'):
            ds_dict = ds.model_dump()
        else:
            ds_dict = {}

        enable = ds_dict.get('oracle_enable_thick_mode')
        path = ds_dict.get('oracle_instant_client_path')

        print(f"oracle_enable_thick_mode: {enable}")
        print(f"oracle_instant_client_path: {path}")

        if enable is None:
            print("\n⚠️  oracle_enable_thick_mode 为 None，检查完整配置:")
            import json
            print(json.dumps(ds_dict, indent=2))
    else:
        print("❌ datasource 配置不存在")

except Exception as e:
    print(f"❌ 配置读取失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试 2: Thick Mode 初始化")
print("=" * 60)

try:
    from derisk_ext.datasource.rdbms.conn_oracle import (
        _init_thick_mode,
        _thick_mode_initialized,
        _thick_mode_failed,
        _find_instant_client_paths
    )

    print(f"初始状态:")
    print(f"  _thick_mode_initialized: {_thick_mode_initialized}")
    print(f"  _thick_mode_failed: {_thick_mode_failed}")

    # 查找所有可能的路径
    print(f"\n自动搜索 Instant Client 路径:")
    found_paths = _find_instant_client_paths()
    if found_paths:
        for p in found_paths:
            exists = os.path.isdir(p)
            print(f"  {p}: {'✅' if exists else '❌'}")
    else:
        print("  未找到")

    # 测试初始化
    instant_client_path = "/opt/oracle/instantclient_11_2"

    print(f"\n检查配置路径: {instant_client_path}")
    print(f"  目录存在: {os.path.isdir(instant_client_path)}")

    if os.path.isdir(instant_client_path):
        print(f"  文件列表:")
        for f in ['libclntsh.so', 'libociei.so', 'libnnz11.so']:
            fp = os.path.join(instant_client_path, f)
            exists = os.path.exists(fp)
            print(f"    {f}: {'✅' if exists else '❌'}")

    print(f"\n调用 _init_thick_mode('{instant_client_path}')...")

    # 设置更详细的日志
    logging.getLogger('derisk_ext.datasource.rdbms.conn_oracle').setLevel(logging.DEBUG)

    success = _init_thick_mode(instant_client_path)

    print(f"\n结果: {'✅ 成功' if success else '❌ 失败'}")
    print(f"最终状态:")
    print(f"  _thick_mode_initialized: {_thick_mode_initialized}")
    print(f"  _thick_mode_failed: {_thick_mode_failed}")

    if not success:
        print(f"\n可能的原因:")
        print(f"  1. Instant Client 路径不正确")
        print(f"  2. 缺少系统依赖库（libaio, libnsl）")
        print(f"  3. 文件权限问题")
        print(f"  4. Instant Client 版本不兼容")

        # 检查是否之前尝试过并失败了
        if _thick_mode_failed:
            print(f"\n⚠️  注意: thick mode 在此进程中已经尝试失败过")
            print(f"   这可能是因为:")
            print(f"   - 之前的初始化尝试失败")
            print(f"   - 或者已经有其他代码用 thin mode 建立了连接")

except ImportError as e:
    print(f"❌ 无法导入 Oracle 模块: {e}")
    print(f"   请确保 derisk-ext 已安装")
except Exception as e:
    print(f"❌ 初始化异常: {e}")
    import traceback
    traceback.print_exc()

EOFPYTHON

# 6. 查看最近的应用日志
echo -e "\n6. 查看应用启动日志中的 OracleInit"
echo "----------------------------------------"
if [ -d "logs" ]; then
    grep -h "OracleInit" logs/*.log 2>/dev/null | tail -20
else
    echo "未找到 logs 目录"
fi

echo -e "\n=========================================="
echo "诊断完成"
echo "=========================================="

echo "
如果 thick mode 初始化失败，请执行以下修复步骤：

1. 安装依赖库:
   sudo apt-get install -y libaio1 libnsl2
   # 或
   sudo yum install -y libaio libnsl

2. 设置环境变量（推荐）:
   export ORACLE_ENABLE_THICK_MODE=true
   export ORACLE_INSTANT_CLIENT_HOME=/opt/oracle/instantclient_11_2
   export LD_LIBRARY_PATH=/opt/oracle/instantclient_11_2:\$LD_LIBRARY_PATH

3. 重启应用
"