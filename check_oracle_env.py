#!/usr/bin/env python3
"""在服务器上运行，检查 Oracle thick mode 配置"""

import os
import sys
import platform

print("=" * 80)
print("Oracle Thick Mode 环境检查")
print("=" * 80)

# 1. 检查环境变量
print("\n1. 检查环境变量")
print("-" * 80)
env_enable = os.environ.get('ORACLE_ENABLE_THICK_MODE', '未设置')
env_client = os.environ.get('ORACLE_INSTANT_CLIENT_HOME', '未设置')
env_oracle_home = os.environ.get('ORACLE_HOME', '未设置')
env_ld_path = os.environ.get('LD_LIBRARY_PATH', '未设置')

print(f"ORACLE_ENABLE_THICK_MODE: {env_enable}")
print(f"ORACLE_INSTANT_CLIENT_HOME: {env_client}")
print(f"ORACLE_HOME: {env_oracle_home}")
print(f"LD_LIBRARY_PATH: {env_ld_path}")

# 2. 查找 derisk.json 文件
print("\n2. 查找 derisk.json 配置文件")
print("-" * 80)

try:
    from derisk_core.config.home import get_derisk_home
    derisk_home = get_derisk_home()
    print(f"DERISK_HOME: {derisk_home}")

    config_file = os.path.join(derisk_home, "derisk.json")
    print(f"配置文件路径: {config_file}")

    if os.path.exists(config_file):
        print(f"✅ 配置文件存在")
        try:
            import json
            with open(config_file, 'r') as f:
                config = json.load(f)

            datasource = config.get('datasource', {})
            enable = datasource.get('oracle_enable_thick_mode', '未设置')
            client_path = datasource.get('oracle_instant_client_path', '未设置')

            print(f"\n配置内容:")
            print(f"  oracle_enable_thick_mode: {enable}")
            print(f"  oracle_instant_client_path: {client_path}")
        except Exception as e:
            print(f"❌ 读取配置失败: {e}")
    else:
        print(f"❌ 配置文件不存在")
except Exception as e:
    print(f"查找配置文件失败: {e}")

# 3. 搜索 Instant Client 安装位置
print("\n3. 搜索 Oracle Instant Client 安装位置")
print("-" * 80)

system = platform.system()
print(f"操作系统: {system}")

# 常见的安装位置
search_paths = []
if system == "Linux":
    search_paths = [
        "/opt/oracle",
        "/usr/lib/oracle",
        "/usr/local/lib/oracle",
        "/usr/lib",
        "/usr/local/lib",
        "/opt",
    ]
elif system == "Darwin":  # macOS
    search_paths = [
        "/opt/oracle",
        "/usr/local/lib",
        "/opt",
        "/usr/local",
    ]

# 添加环境变量中的路径
for env_var in ['ORACLE_INSTANT_CLIENT_HOME', 'ORACLE_HOME']:
    env_path = os.environ.get(env_var)
    if env_path:
        search_paths.insert(0, env_path)

print("\n搜索以下路径:")
found_paths = []
for path in search_paths:
    if not os.path.isdir(path):
        continue

    print(f"\n检查: {path}")

    try:
        # 查找 instantclient 子目录
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if 'instantclient' in entry.lower() and os.path.isdir(full_path):
                print(f"  ✅ 找到: {full_path}")
                found_paths.append(full_path)

                # 检查关键文件
                for key_file in ['libclntsh.so', 'libociei.so', 'oci.dll', 'libclntsh.dylib']:
                    key_path = os.path.join(full_path, key_file)
                    if os.path.exists(key_path):
                        print(f"     包含: {key_file} ✅")

                # 检查版本文件
                version_file = os.path.join(full_path, 'network', 'admin', 'sqlnet.ora')
                if os.path.exists(version_file):
                    print(f"     包含: network/admin/sqlnet.ora")
    except PermissionError:
        print(f"  ⚠️  无权限访问")
    except Exception as e:
        print(f"  ❌ 检查失败: {e}")

if not found_paths:
    print("\n❌ 未找到 Instant Client")
    print("\n可能的安装方法:")
    if system == "Linux":
        print("""
方法 1: 下载并解压
  wget https://download.oracle.com/otn_software/linux/instantclient/11204/instantclient-basic-linux.x64-11.2.0.4.0.zip
  unzip instantclient-basic-linux.x64-11.2.0.4.0.zip -d /opt/oracle
  export ORACLE_INSTANT_CLIENT_HOME=/opt/oracle/instantclient_11_2

方法 2: 使用包管理器
  # Ubuntu/Debian
  sudo apt-get install libaio1
  # 然后下载安装 Instant Client

方法 3: 检查是否在其他位置
  find / -name "libclntsh.so" 2>/dev/null
""")
    elif system == "Darwin":
        print("""
方法 1: 使用 Homebrew
  brew install instantclient

方法 2: 手动下载
  从 Oracle 官网下载 macOS 版本的 Instant Client
""")

# 4. 测试 thick mode 初始化
print("\n4. 测试 Oracle thick mode 初始化")
print("-" * 80)

try:
    sys.path.insert(0, 'packages/derisk-ext/src')
    from derisk_ext.datasource.rdbms.conn_oracle import _init_thick_mode, _thick_mode_initialized

    print(f"当前状态: initialized={_thick_mode_initialized}")

    if found_paths:
        test_path = found_paths[0]
        print(f"\n尝试初始化: {test_path}")
        success = _init_thick_mode(test_path)
        if success:
            print("✅ Thick mode 初始化成功")
        else:
            print("❌ Thick mode 初始化失败")
    else:
        print("\n尝试使用系统默认路径初始化")
        success = _init_thick_mode()
        if success:
            print("✅ Thick mode 初始化成功")
        else:
            print("❌ Thick mode 初始化失败")

except ImportError as e:
    print(f"❌ 无法导入 Oracle 模块: {e}")
except Exception as e:
    print(f"❌ 初始化异常: {e}")
    import traceback
    traceback.print_exc()

# 5. 建议
print("\n" + "=" * 80)
print("配置建议")
print("=" * 80)

if found_paths:
    client_path = found_paths[0]
    print(f"""
✅ 找到 Instant Client: {client_path}

方案 1: 设置环境变量（推荐）
---------------------------
在启动应用前执行：

export ORACLE_ENABLE_THICK_MODE=true
export ORACLE_INSTANT_CLIENT_HOME={client_path}

或者写入到 ~/.bashrc 或 ~/.zshrc：

echo 'export ORACLE_ENABLE_THICK_MODE=true' >> ~/.bashrc
echo 'export ORACLE_INSTANT_CLIENT_HOME={client_path}' >> ~/.bashrc
source ~/.bashrc

方案 2: 配置 derisk.json
-----------------------
编辑 {config_file}，添加：

{{
  "datasource": {{
    "oracle_enable_thick_mode": true,
    "oracle_instant_client_path": "{client_path}"
  }}
}}

如果文件不存在，创建它：
mkdir -p {os.path.dirname(config_file)}
""")
else:
    print("""
❌ 未找到 Instant Client

请先安装 Oracle Instant Client：
1. 从 Oracle 官网下载：https://www.oracle.com/database/technologies/instant-client/downloads.html
2. 选择 Basic 或 Basic Light 版本
3. 解压到一个固定目录（如 /opt/oracle/instantclient_11_2）
4. 重新运行此脚本检查
""")

print("\n完成后重启应用测试！")