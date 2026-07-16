#!/usr/bin/env python3
"""详细诊断 Oracle thick mode 初始化失败的原因"""

import os
import sys
import logging

# 启用详细日志
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

print("=" * 80)
print("Oracle Thick Mode 初始化详细诊断")
print("=" * 80)

# 1. 检查配置读取
print("\n1. 检查配置读取")
print("-" * 80)

try:
    from derisk_core.config import ConfigManager

    config = ConfigManager.get()
    print(f"✅ ConfigManager.get() 成功")

    if hasattr(config, 'datasource') and config.datasource:
        ds = config.datasource
        print(f"✅ datasource 配置存在")

        # 使用 model_dump() 获取所有字段
        ds_dict = ds.model_dump() if hasattr(ds, 'model_dump') else {}
        enable = ds_dict.get('oracle_enable_thick_mode')
        client_path = ds_dict.get('oracle_instant_client_path')

        print(f"  oracle_enable_thick_mode: {enable} (type: {type(enable)})")
        print(f"  oracle_instant_client_path: {client_path} (type: {type(client_path)})")

        # 也尝试 getattr
        enable_attr = getattr(ds, 'oracle_enable_thick_mode', None)
        client_attr = getattr(ds, 'oracle_instant_client_path', None)

        print(f"  oracle_enable_thick_mode (getattr): {enable_attr}")
        print(f"  oracle_instant_client_path (getattr): {client_attr}")

    else:
        print("❌ datasource 配置不存在")

except Exception as e:
    print(f"❌ 读取配置失败: {e}")
    import traceback
    traceback.print_exc()

# 2. 检查 Instant Client 路径
print("\n2. 检查 Instant Client 路径")
print("-" * 80)

instant_client_path = "/opt/oracle/instantclient_11_2"
print(f"路径: {instant_client_path}")
print(f"存在: {os.path.isdir(instant_client_path)}")

if os.path.isdir(instant_client_path):
    print(f"✅ 目录存在")

    # 列出关键文件
    key_files = [
        'libclntsh.so',
        'libociei.so',
        'libnnz11.so',
        'libocci.so.11.1',
        'libsqlplus.so',
    ]

    print(f"\n关键文件检查:")
    for f in key_files:
        path = os.path.join(instant_client_path, f)
        exists = os.path.exists(path)
        print(f"  {f}: {'✅' if exists else '❌'}")

    # 检查权限
    print(f"\n权限检查:")
    print(f"  目录权限: {oct(os.stat(instant_client_path).st_mode)}")

    # 尝试读取 libclntsh.so
    lib_path = os.path.join(instant_client_path, 'libclntsh.so')
    if os.path.exists(lib_path):
        print(f"  libclntsh.so 权限: {oct(os.stat(lib_path).st_mode)}")

# 3. 测试初始化
print("\n3. 测试 thick mode 初始化")
print("-" * 80)

try:
    sys.path.insert(0, 'packages/derisk-ext/src')
    from derisk_ext.datasource.rdbms.conn_oracle import _init_thick_mode

    print(f"调用 _init_thick_mode('{instant_client_path}')")

    # 捕获详细的错误信息
    import oracledb
    print(f"oracledb 版本: {oracledb.__version__}")

    # 检查是否已经初始化
    if hasattr(oracledb, 'is_thin_mode'):
        is_thin = oracledb.is_thin_mode()
        print(f"当前模式: {'thin' if is_thin else 'thick'}")

    # 尝试初始化
    try:
        oracledb.init_oracle_client(lib_dir=instant_client_path)
        print("✅ init_oracle_client 成功")
    except Exception as e:
        print(f"❌ init_oracle_client 失败: {e}")
        print(f"错误类型: {type(e).__name__}")

        # 常见错误的解决方法
        error_msg = str(e)
        if "libaio" in error_msg.lower() or "libaio.so" in error_msg.lower():
            print("\n💡 解决方法: 安装 libaio 库")
            print("   Ubuntu/Debian: sudo apt-get install -y libaio1")
            print("   CentOS/RHEL: sudo yum install -y libaio")
        elif "Permission denied" in error_msg:
            print("\n💡 解决方法: 检查文件权限")
            print(f"   sudo chmod -R 755 {instant_client_path}")
        elif "not found" in error_msg.lower():
            print("\n💡 解决方法: 检查库文件是否完整")
            print(f"   ls -la {instant_client_path}/lib*.so*")

except ImportError as e:
    print(f"❌ 导入 oracledb 失败: {e}")
except Exception as e:
    print(f"❌ 初始化异常: {e}")
    import traceback
    traceback.print_exc()

# 4. 检查系统依赖
print("\n4. 检查系统依赖")
print("-" * 80)

import subprocess

print("检查 libaio:")
result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True)
if 'libaio.so' in result.stdout:
    print("✅ libaio 已安装")
    for line in result.stdout.split('\n'):
        if 'libaio' in line:
            print(f"  {line.strip()}")
else:
    print("❌ libaio 未安装")
    print("\n安装命令:")
    print("  Ubuntu/Debian: sudo apt-get install -y libaio1")
    print("  CentOS/RHEL: sudo yum install -y libaio")

print("\n检查其他依赖:")
deps = ['libnsl.so.1', 'libnsl.so.2']
for dep in deps:
    if dep in result.stdout:
        print(f"✅ {dep} 存在")
    else:
        print(f"⚠️  {dep} 不存在（可能需要安装）")

# 5. 建议
print("\n" + "=" * 80)
print("建议的修复步骤")
print("=" * 80)

print("""
1. 确保安装了所有依赖库:
   sudo apt-get install -y libaio1 libnsl2  # Ubuntu/Debian
   sudo yum install -y libaio libnsl       # CentOS/RHEL

2. 设置正确的环境变量:
   export ORACLE_ENABLE_THICK_MODE=true
   export ORACLE_INSTANT_CLIENT_HOME=/opt/oracle/instantclient_11_2
   export LD_LIBRARY_PATH=/opt/oracle/instantclient_11_2:$LD_LIBRARY_PATH

3. 检查文件权限:
   sudo chmod -R 755 /opt/oracle/instantclient_11_2

4. 重启应用并查看详细日志
""")