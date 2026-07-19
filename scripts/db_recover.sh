#!/bin/bash
# scripts/db_recover.sh
# 从损坏的 SQLite 库中安全恢复数据(database disk image is malformed)。
#
# 策略:全程绝不就地操作原文件 -> 先物理双备份 -> .recover 页级抽取 -> 重建干净库
#       -> 完整性校验 + 逐表行数对比 -> 输出新库路径,人工确认后手动替换。
#
# .recover 比 .dump 强:遇到坏页自动跳过继续,并把找不到归属表的行收进
# lost_and_found 表,抢救率最高。坏掉的 CREATE TABLE 在替换后由 app 启动时
# 的 create_all / _add_missing_columns_sqlite 自动补齐(空表)。
#
# 用法:
#   ./scripts/db_recover.sh [db_path]
#   DERISK_DB_PATH=/data/derisk.db ./scripts/db_recover.sh
#
# 环境变量:
#   DERISK_DB_PATH  数据库路径(默认 <repo>/pilot/meta_data/derisk.db)
#
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'
CHECK="✓"; WARN="⚠"; ERROR="✗"; INFO="ℹ"

info()  { printf "${BLUE}${INFO}${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}${CHECK}${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}${WARN}${NC}  %s\n" "$*"; }
die()   { printf "${RED}${ERROR}${NC} %s\n" "$*"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DB="${1:-${DERISK_DB_PATH:-$REPO_ROOT/pilot/meta_data/derisk.db}}"
[ -f "$DB" ] || die "数据库不存在: $DB (可用 DERISK_DB_PATH 或第一个参数指定)"
command -v sqlite3 >/dev/null 2>&1 || die "缺少 sqlite3 命令(需 >=3.29 才有 .recover)"
# timeout 用于防止查询卡死在坏页上;macOS 默认无此命令,降级为不加超时
if command -v timeout >/dev/null 2>&1; then
    _guard() { timeout 60 "$@"; }
else
    _guard() { "$@"; }
fi

DBDIR="$(cd "$(dirname "$DB")" && pwd)"
DBNAME="$(basename "$DB")"
TS="$(date +%Y%m%d_%H%M%S)"
WORK="$DBDIR/recover_$TS"

printf "\n${BOLD}${BLUE}==== SQLite 损坏恢复 ====${NC}\n"
info "源库:   $DB"
info "工作区: $WORK"
warn "确认服务已停止,没有进程占用 $DBNAME"
read -r -p "继续? [y/N] " ans
[ "$ans" = "y" ] || [ "$ans" = "Y" ] || die "已取消"

mkdir -p "$WORK"

# 1. 物理双备份:原文件 + WAL + SHM(WAL 里有已提交未 checkpoint 的数据,必须一起备份)
info "[1/6] 物理备份原始文件"
cp "$DB" "$DB.prerecover_$TS"
cp "$DB" "$WORK/original.db"
[ -f "$DB-wal" ] && cp "$DB-wal" "$WORK/original.db-wal" || true
[ -f "$DB-shm" ] && cp "$DB-shm" "$WORK/original.db-shm" || true
ok "原文件已备份: $DB.prerecover_$TS (就地留底,方便回滚)"

# 2. .recover 页级抽取
#    关键:.recover 遇到坏页会返回非零退出码,但仍会输出已恢复的数据(这是正常行为!)。
#    只要产出了 SQL 就必须保留 -- 绝不能因非零退出而丢弃改用 .dump(.dump 遇坏页即停,抢救率远差)。
info "[2/6] 执行 .recover 抽取数据"
RECOVER_LOG="$WORK/recover.log"
sqlite3 "$WORK/original.db" ".recover" > "$WORK/recovered.sql" 2> "$RECOVER_LOG" || true
LINES="$(wc -l < "$WORK/recovered.sql" | xargs)"
if [ "$LINES" -lt 5 ]; then
    warn ".recover 几乎无输出(仅 $LINES 行),改用 .dump 兜底"
    sqlite3 "$WORK/original.db" ".dump" > "$WORK/recovered.sql" 2>> "$RECOVER_LOG" || true
    LINES="$(wc -l < "$WORK/recovered.sql" | xargs)"
else
    ok "抽取 SQL 行数: $LINES (.recover 对坏库返回非零属正常,已保留全部输出)"
fi
# grep -c 无匹配时会打印 0 并返回非零,用 || true 避免 set -e 退出;空值兜底为 0
ERRCNT="$(grep -ci 'error\|malformed' "$RECOVER_LOG" 2>/dev/null || true)"
ERRCNT="${ERRCNT:-0}"
[ "$ERRCNT" -gt 0 ] && warn "恢复日志中有 $ERRCNT 条错误/警告(坏页,部分行可能丢失)"

# 3. 用 recovered.sql 重建干净库(单条语句失败不影响其余,sqlite3 默认不停)
info "[3/6] 重建干净库"
NEWDB="$WORK/recovered.db"
rm -f "$NEWDB" "$NEWDB-wal" "$NEWDB-shm"
sqlite3 "$NEWDB" < "$WORK/recovered.sql" 2> "$WORK/rebuild.log" || true
ok "新库: $NEWDB"

# 4. 完整性校验
info "[4/6] 完整性校验"
STATUS="$(sqlite3 "$NEWDB" "PRAGMA integrity_check;" 2>/dev/null || echo "error")"
if [ "$STATUS" = "ok" ]; then
    ok "integrity_check: ok"
else
    warn "integrity_check: $STATUS (新库仍可能有不一致,请仔细核对行数)"
fi

# 5. 逐表行数对比(旧库能查的表才对比,加 timeout 防卡死在坏页上)
info "[5/6] 逐表行数对比(旧 vs 新)"
TABLES="$(sqlite3 "$NEWDB" \
  "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'lost_and_found%' ORDER BY name;")"
printf "  %-42s %-12s %s\n" "TABLE" "OLD" "NEW"
printf "  %-42s %-12s %s\n" "----------------------------------------" "----------" "----------"
while IFS= read -r t; do
    [ -z "$t" ] && continue
    OLD="$(_guard sqlite3 "$WORK/original.db" "SELECT count(*) FROM \"$t\";" 2>/dev/null || echo "ERR(坏页)")"
    NEW="$(sqlite3 "$NEWDB" "SELECT count(*) FROM \"$t\";" 2>/dev/null || echo "ERR")"
    MARK=""
    if [ "$OLD" != "ERR(坏页)" ] && [ "$NEW" != "ERR" ] && [ "$OLD" != "$NEW" ]; then
        MARK="  <- 差异(旧库可能含坏页,新库以可读页为准)"
    fi
    printf "  %-42s %-12s %s%s\n" "$t" "$OLD" "$NEW" "$MARK"
done <<< "$TABLES"

LAF="$(sqlite3 "$NEWDB" "SELECT count(*) FROM lost_and_found;" 2>/dev/null || echo 0)"
echo ""
info "lost_and_found(.recover 无法归类的孤儿行): $LAF"
if [ "$LAF" -gt 0 ]; then
    warn "schema 页损坏导致数据无法归位到原表,全部进了 lost_and_found(数据未丢,需后续归位)"
    info "按 rootpgno 分组(每个 rootpgno 通常对应一张原表),用于后续把数据归回正确表:"
    sqlite3 -header -column "$NEWDB" \
      "SELECT rootpgno, nfield, count(*) AS rows FROM lost_and_found GROUP BY rootpgno, nfield ORDER BY rootpgno;" 2>/dev/null || true
    echo ""
    # 动态取 lost_and_found 实际存在的数据列(前 5 个),避免写死 cN 导致列不存在报错
    DATA_COLS="$(sqlite3 "$NEWDB" \
      "SELECT group_concat(name, ', ') FROM (SELECT name FROM pragma_table_info('lost_and_found') WHERE name LIKE 'c%' ORDER BY CAST(substr(name,2) AS INTEGER) LIMIT 5);" 2>/dev/null || true)"
    if [ -n "$DATA_COLS" ]; then
        info "抽样查看每个 rootpgno 的数据形态(帮助识别是哪张表):"
        sqlite3 -header -column "$NEWDB" \
          "SELECT rootpgno, nfield, $DATA_COLS FROM lost_and_found GROUP BY rootpgno ORDER BY rootpgno LIMIT 50;" 2>/dev/null || true
    fi
fi

# 6. 输出替换指引(绝不自动覆盖)
printf "\n${BOLD}${GREEN}==== 恢复完成 ====${NC}\n"
printf "新库: ${BOLD}%s${NC}\n" "$NEWDB"
printf "旧库留底: %s\n" "$DB.prerecover_$TS"
# heredoc 不解析 \033 转义,颜色行用 printf 单独输出
printf "\n${YELLOW}下一步(人工确认行数无误后执行,切勿自动覆盖):${NC}\n\n"
cat <<EOF
  # 1. 再留一份当前库(双保险)
  cp "$DB" "$DB.before_swap_$TS"

  # 2. 清掉旧 WAL/SHM(避免读到坏页),替换主库
  rm -f "$DB-wal" "$DB-shm"
  cp "$NEWDB" "$DB"

  # 3. 启动服务 -- app 会自动 create_all 补齐 .recover 漏掉的空表/缺列
  #    ./scripts/start_server.sh

  # 4. 若 lost_and_found 还有大量未归类行,可用 undark 二次抢救:
  #    https://github.com/forensicmatt/undark

  # 回滚(如新库有问题):
  cp "$DB.prerecover_$TS" "$DB"
EOF
printf "\n"
