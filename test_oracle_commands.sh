#!/bin/bash
# Oracle Instant Client 命令验证

echo "=========================================="
echo "Oracle Instant Client 命令验证"
echo "=========================================="

echo -e "\n1. 查找 Oracle 命令工具"
echo "----------------------------------------"

# 搜索常见的 Oracle 命令
COMMANDS=("sqlplus" "tnsping" "lsnrctl" "imp" "exp" "sqlldr" "rman")

for cmd in "${COMMANDS[@]}"; do
    echo -e "\n检查 $cmd:"
    if command -v $cmd &> /dev/null; then
        echo "  ✅ 找到: $(which $cmd)"
        # 尝试获取版本
        case $cmd in
            sqlplus)
                echo "  版本信息:"
                $cmd -V 2>&1 | head -3 || echo "  无法获取版本"
                ;;
            tnsping)
                echo "  用法: tnsping <host>:<port>/<service_name>"
                ;;
        esac
    else
        echo "  ❌ 未找到 $cmd"

        # 尝试在常见路径中查找
        for path in "${ORACLE_INSTANT_CLIENT_HOME:-/opt/oracle/instantclient_11_2}" \
                    "/opt/oracle/instantclient"* \
                    "/usr/lib/oracle/instantclient"*; do
            if [ -d "$path" ]; then
                if [ -f "$path/bin/$cmd" ] || [ -f "$path/$cmd" ]; then
                    echo "  找到但未在 PATH 中: $path/$cmd"
                    echo "  建议: export PATH=\$PATH:$path"
                    if [ -f "$path/$cmd" ]; then
                        echo "  或: export PATH=\$PATH:$path"
                    fi
                fi
            fi
        done
    fi
done

echo -e "\n\n2. 测试 Oracle 连接（如果 sqlplus 可用）"
echo "----------------------------------------"

if command -v sqlplus &> /dev/null; then
    echo "sqlplus 可用，可以测试连接"
    echo ""
    echo "使用方法:"
    echo "  sqlplus username/password@host:port/service_name"
    echo ""
    echo "示例:"
    echo "  sqlplus scott/tiger@172.20.2.247:1521/ORCL"
    echo ""
    echo "或者使用 TNS 别名（如果配置了 tnsnames.ora）:"
    echo "  sqlplus scott/tiger@ORCL"
    echo ""
    echo "测试连接（不登录）:"
    echo "  sqlplus /nolog"
else
    echo "❌ sqlplus 未安装或不在 PATH 中"
fi

echo -e "\n\n3. 使用 tnsping 测试连接（不需要密码）"
echo "----------------------------------------"

if command -v tnsping &> /dev/null; then
    echo "tnsping 可用，可以测试监听器"
    echo ""
    echo "使用方法:"
    echo "  tnsping host:port/service_name"
    echo ""
    echo "示例:"
    echo "  tnsping 172.20.2.247:1521/ORCL"
    echo ""
    read -p "要测试连接吗？输入 host:port/service_name: " conn_string
    if [ -n "$conn_string" ]; then
        echo "执行: tnsping $conn_string"
        tnsping "$conn_string"
    fi
else
    echo "❌ tnsping 未安装或不在 PATH 中"
fi

echo -e "\n\n4. 检查环境变量"
echo "----------------------------------------"

echo "PATH 中包含的 Oracle 路径:"
echo "$PATH" | tr ':' '\n' | grep -i oracle || echo "  未找到 Oracle 路径"

echo -e "\nORACLE 相关环境变量:"
env | grep -i oracle || echo "  未设置"

echo -e "\n\n=========================================="
echo "建议"
echo "=========================================="

if ! command -v sqlplus &> /dev/null; then
    echo "
如果找到 sqlplus 但不在 PATH 中：

# 假设 Instant Client 安装在 /opt/oracle/instantclient_11_2
export PATH=\$PATH:/opt/oracle/instantclient_11_2
export LD_LIBRARY_PATH=/opt/oracle/instantclient_11_2:\$LD_LIBRARY_PATH

# 然后测试
sqlplus -V
"
fi

echo "
常用验证命令：

1. 检查 sqlplus 版本:
   sqlplus -V

2. 测试数据库连接（需要用户名密码）:
   sqlplus username/password@host:port/service_name

3. 测试监听器（不需要密码）:
   tnsping host:port/service_name

4. 查看 Oracle 版本信息:
   sqlplus -V

5. 查看环境变量:
   echo \$ORACLE_HOME
   echo \$LD_LIBRARY_PATH
"