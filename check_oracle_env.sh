#!/bin/bash
# 在服务器上运行这个脚本

echo "=========================================="
echo "Oracle 环境检查"
echo "=========================================="

echo -e "\n1. 检查环境变量"
echo "----------------------------------------"
echo "ORACLE_ENABLE_THICK_MODE: ${ORACLE_ENABLE_THICK_MODE:-未设置}"
echo "ORACLE_INSTANT_CLIENT_HOME: ${ORACLE_INSTANT_CLIENT_HOME:-未设置}"
echo "ORACLE_HOME: ${ORACLE_HOME:-未设置}"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH:-未设置}"

echo -e "\n2. 查找 derisk.json 文件"
echo "----------------------------------------"
DERISK_HOME="${HOME}/.derisk"
CONFIG_FILE="${DERISK_HOME}/derisk.json"
echo "DERISK_HOME: ${DERISK_HOME}"
echo "配置文件: ${CONFIG_FILE}"

if [ -f "${CONFIG_FILE}" ]; then
    echo "✅ 配置文件存在"
    echo "内容:"
    cat "${CONFIG_FILE}"
else
    echo "❌ 配置文件不存在"
fi

echo -e "\n3. 搜索 Instant Client"
echo "----------------------------------------"

# 搜索常见位置
SEARCH_DIRS=(
    "/opt/oracle"
    "/usr/lib/oracle"
    "/usr/local/lib/oracle"
    "/opt"
    "/usr/lib"
    "/usr/local/lib"
)

FOUND=""

for dir in "${SEARCH_DIRS[@]}"; do
    if [ -d "${dir}" ]; then
        # 查找包含 instantclient 的子目录
        find "${dir}" -type d -name "*instantclient*" 2>/dev/null | while read -r path; do
            echo "找到: ${path}"
            if [ -f "${path}/libclntsh.so" ] || [ -f "${path}/libociei.so" ]; then
                echo "  ✅ 包含关键库文件"
                FOUND="${path}"
            fi
        done
    fi
done

# 使用 locate 或 find 搜索
if [ -z "${FOUND}" ]; then
    echo -e "\n未找到，尝试全局搜索（需要几分钟）..."
    sudo find / -name "libclntsh.so" 2>/dev/null | head -5
fi

echo -e "\n4. 检查是否可以找到 oracledb 模块"
echo "----------------------------------------"
python3 -c "import oracledb; print(f'oracledb version: {oracledb.__version__}')" 2>&1 || echo "❌ 未安装 oracledb 模块"

echo -e "\n=========================================="
echo "建议操作"
echo "=========================================="

if [ -n "${FOUND}" ]; then
    echo "
方案 1: 设置环境变量（推荐）

export ORACLE_ENABLE_THICK_MODE=true
export ORACLE_INSTANT_CLIENT_HOME=${FOUND}

方案 2: 创建/编辑配置文件

mkdir -p ${DERISK_HOME}
cat > ${CONFIG_FILE} << EOF
{
  \"datasource\": {
    \"oracle_enable_thick_mode\": true,
    \"oracle_instant_client_path\": \"${FOUND}\"
  }
}
EOF

cat ${CONFIG_FILE}
"
else
    echo "
❌ 未找到 Instant Client

请安装 Oracle Instant Client:
1. 从 Oracle 官网下载：https://www.oracle.com/database/technologies/instant-client/downloads.html
2. 选择 Basic 或 Basic Light 版本（11.2 或更高）
3. 解压到固定目录（如 /opt/oracle/instantclient_11_2）
"
fi