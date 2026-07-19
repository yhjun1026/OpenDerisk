#!/bin/bash
# scripts/db_backup.sh
# SQLite 在线一致性备份 -- 服务运行中也可安全执行,产出事务一致的快照单文件。
#
# 用法:
#   ./scripts/db_backup.sh [db_path] [backup_dir]
#   DERISK_DB_PATH=/data/derisk.db ./scripts/db_backup.sh
#
# 定时任务(crontab,每小时一次):
#   0 * * * * /home/code/OpenDerisk-main/scripts/db_backup.sh >> /var/log/derisk_backup.log 2>&1
#
# 环境变量:
#   DERISK_DB_PATH     数据库路径(默认 <repo>/pilot/meta_data/derisk.db)
#   DERISK_BACKUP_DIR  备份目录(默认 <repo>/pilot/meta_data/backups)
#   DERISK_KEEP_DAYS   本地保留天数(默认 7)
#   DERISK_REMOTE      可选,异机 rsync 目标,如 "backup-host:/backups/derisk/"
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
BACKUP_DIR="${2:-${DERISK_BACKUP_DIR:-$REPO_ROOT/pilot/meta_data/backups}}"
KEEP_DAYS="${DERISK_KEEP_DAYS:-7}"

[ -f "$DB" ] || die "数据库不存在: $DB (可用 DERISK_DB_PATH 或第一个参数指定)"
command -v sqlite3 >/dev/null 2>&1 || die "缺少 sqlite3 命令,请先安装"
mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M)"
DEST="$BACKUP_DIR/derisk_$TS.db"
TMP="$DEST.tmp"

printf "\n${BOLD}${BLUE}==== SQLite 在线备份 ====${NC}\n"
info "源库:   $DB"
info "备份到: $BACKUP_DIR"
info "保留:   ${KEEP_DAYS} 天"

# 1. 在线一致性快照(.backup 会在运行中的库上做事务一致拷贝,无需停服)
info "执行 .backup ..."
if ! sqlite3 "$DB" ".backup $TMP" 2>/dev/null; then
    rm -f "$TMP"
    die "备份失败,可能是库已损坏 -> 用 scripts/db_recover.sh 修复后再备份"
fi
mv "$TMP" "$DEST"
ok "快照完成: $DEST"

# 2. 校验备份文件完整性(只校验备份,不动主库)
STATUS="$(sqlite3 "$DEST" "PRAGMA integrity_check;" 2>/dev/null || echo error)"
if [ "$STATUS" = "ok" ]; then
    ok "完整性校验通过"
else
    warn "备份完整性校验失败: $STATUS (备份仍保留,但建议检查主库)"
fi

# 3. 本地保留期清理
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -name 'derisk_*.db' -mtime +"$KEEP_DAYS" -print -delete 2>/dev/null | wc -l | xargs)"
info "清理 ${KEEP_DAYS} 天前的旧备份: 删除 ${DELETED} 个"

# 4. 可选:异机 rsync(防整盘故障)
if [ -n "${DERISK_REMOTE:-}" ]; then
    info "异机同步到: $DERISK_REMOTE"
    if rsync -az --delete "$BACKUP_DIR/" "$DERISK_REMOTE" 2>/dev/null; then
        ok "异机同步完成"
    else
        warn "异机同步失败(本地备份仍有效)"
    fi
fi

# 5. 汇总
SIZE="$(du -h "$DEST" | cut -f1)"
COUNT="$(find "$BACKUP_DIR" -maxdepth 1 -name 'derisk_*.db' | wc -l | xargs)"
printf "\n${GREEN}${CHECK} 备份成功${NC}  文件=%s  大小=%s  本地共 %s 份\n" "$DEST" "$SIZE" "$COUNT"
