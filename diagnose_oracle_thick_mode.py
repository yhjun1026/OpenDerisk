#!/usr/bin/env python3
"""诊断 Oracle thick mode 配置和初始化

使用方法：
    uv run python diagnose_oracle_thick_mode.py
"""

import sys
import os

sys.path.insert(0, 'packages/derisk-core/src')
sys.path.insert(0, 'packages/derisk-serve/src')
sys.path.insert(0, 'packages/derisk-app/src')
sys.path.insert(0, 'packages/derisk-ext/src')

def diagnose():
    print("=" * 80)
    print("Oracle Thick Mode 配置诊断")
    print("=" * 80)

    # 1. 检查环境变量
    print("\n1. 检查环境变量")
    print("-" * 80)
    env_enable = os.environ.get('ORACLE_ENABLE_THICK_MODE', '未设置')
    env_client = os.environ.get('ORACLE_INSTANT_CLIENT_HOME', '未设置')
    print(f"ORACLE_ENABLE_THICK_MODE: {env_enable}")
    print(f"ORACLE_INSTANT_CLIENT_HOME: {env_client}")

    # 2. 检查 derisk.json 配置
    print("\n2. 检查 derisk.json 配置")
    print("-" * 80)
    try:
        from derisk_core.config import ConfigManager

        config = ConfigManager.get()
        if config and hasattr(config, 'datasource') and config.datasource:
            enable = getattr(config.datasource, 'oracle_enable_thick_mode', None)
            client_path = getattr(config.datasource, 'oracle_instant_client_path', None)
            print(f"oracle_enable_thick_mode: {enable}")
            print(f"oracle_instant_client_path: {client_path}")
        else:
            print("未找到 datasource 配置")
    except Exception as e:
        print(f"读取配置失败: {e}")

    # 3. 检查数据库配置
    print("\n3. 检查数据库配置（System Config）")
    print("-" * 80)
    try:
        from derisk_serve.config.service.service import get_config_by_key

        db_enable = get_config_by_key('oracle_enable_thick_mode')
        db_client = get_config_by_key('oracle_instant_client_path')
        print(f"oracle_enable_thick_mode: {db_enable or '未设置'}")
        print(f"oracle_instant_client_path: {db_client or '未设置'}")
    except Exception as e:
        print(f"读取数据库配置失败: {e}")

    # 4. 测试 thick mode 初始化
    print("\n4. 测试 Oracle thick mode 初始化")
    print("-" * 80)
    try:
        from derisk_ext.datasource.rdbms.conn_oracle import _init_thick_mode, _find_instant_client_paths

        # 查找可能的 Instant Client 路径
        print("\n自动搜索 Instant Client 路径:")
        found_paths = _find_instant_client_paths()
        if found_paths:
            for path in found_paths:
                exists = os.path.isdir(path)
                print(f"  - {path} {'✅ 存在' if exists else '❌ 不存在'}")
        else:
            print("  ❌ 未找到 Instant Client 路径")

        # 尝试初始化 thick mode
        print("\n尝试初始化 thick mode:")
        success = _init_thick_mode()
        if success:
            print("✅ Thick mode 初始化成功")
        else:
            print("❌ Thick mode 初始化失败")
            print("\n可能的原因：")
            print("  1. Instant Client 未安装")
            print("  2. 未设置 ORACLE_INSTANT_CLIENT_HOME 环境变量")
            print("  3. 未在 derisk.json 中配置 oracle_instant_client_path")

    except ImportError as e:
        print(f"❌ 无法导入 Oracle 模块: {e}")
    except Exception as e:
        print(f"❌ Thick mode 初始化异常: {e}")
        import traceback
        traceback.print_exc()

    # 5. 建议
    print("\n" + "=" * 80)
    print("建议的修复方案")
    print("=" * 80)
    print("""
方案 1：配置 derisk.json（推荐）
--------------------------------
编辑 ~/.derisk/derisk.json，添加：

{
  "datasource": {
    "oracle_enable_thick_mode": true,
    "oracle_instant_client_path": "/path/to/instantclient_11_2"
  }
}

方案 2：设置环境变量
------------------
export ORACLE_ENABLE_THICK_MODE=true
export ORACLE_INSTANT_CLIENT_HOME=/path/to/instantclient_11_2

方案 3：检查数据库配置（如果使用 System Config 管理）
----------------------------------------------------
通过管理界面或 API 设置：
  - oracle_enable_thick_mode = true
  - oracle_instant_client_path = /path/to/instantclient_11_2

重要提示
========
对于 Oracle 11g，thick mode 是必须的！
python-oracledb thin mode 不支持 Oracle 11c 及更早版本。
""")

if __name__ == "__main__":
    diagnose()