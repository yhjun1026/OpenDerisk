#!/usr/bin/env python3
"""db_reconstruct.py - 从 .recover 的 lost_and_found 重建 derisk.db

背景:derisk.db 的 schema 页(sqlite_master)损坏,.recover 把全部数据塞进
lost_and_found(带 rootpgno 标识来源表,值在 c0..cN)。本工具:

  analyze : 用 app 的 create_all 生成空 schema,分析 lost_and_found 的 rootpgno
            分布,按列数匹配 rootpgno -> 表,输出建议。
  load    : 把 lost_and_found 的数据按 rootpgno 灌回正确的表,产出可用的库。

nfield 语义(实测):derisk 表均为 id=INTEGER PRIMARY KEY(rowid 别名),
  - nfield = 声明列数(含 id)
  - c0 = NULL(id 位置,真实值在 lost_and_found.id)
  - c1..c(N-1) = 其余列,按声明顺序
  - 尾部 NULL 列在记录里省略,c{i} 缺失时自动为 NULL
  故灌回时:target.id <- lost_and_found.id,其余列 i <- c{i}

用法(服务器 repo 根目录,需 derisk venv):
  # 1. 分析
  uv run python scripts/db_reconstruct.py analyze \
      --recovered pilot/meta_data/recover_20260719_222336/recovered.db \
      --fresh pilot/meta_data/fresh_schema.db
  # 2. 重建(自动匹配 + 灌数据)
  uv run python scripts/db_reconstruct.py load \
      --fresh pilot/meta_data/fresh_schema.db \
      --recovered pilot/meta_data/recover_20260719_222336/recovered.db \
      --out pilot/meta_data/reconstructed.db
  # 3.(可选)人工 mapping 覆盖自动匹配不了的 rootpgno
  uv run python scripts/db_reconstruct.py load ... --mapping mapping.json
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys

SCHEMA_TYPES = {"table", "index", "view", "trigger"}

# 分析后填入:列数冲突的 rootpgno -> {table, sources[]}。
# sources 为目标表各列(按声明顺序)在 lost_and_found 的来源,通常:
#   IPK(id,首列 INTEGER PRIMARY KEY)位置用 "id",其余列 i 用 "c{i}"。
# 例:{"101": {"table": "system_config", "sources": ["id","c1","c2","c3","c4","c5","c6"]}}
DEFAULT_MAPPING = {}


def setup_paths():
    d = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(d)
    for pkg in ("derisk-app", "derisk-core", "derisk-serve", "derisk-ext", "derisk-client"):
        p = os.path.join(root, "packages", pkg, "src")
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


def create_fresh_schema(fresh_path):
    setup_paths()
    for ext in ("", "-wal", "-shm"):
        p = fresh_path + ext
        if os.path.exists(p):
            os.remove(p)
    from derisk.storage.metadata.db_manager import initialize_db, db
    from derisk_app.initialization.db_model_initialization import _MODELS  # noqa: F401

    initialize_db(f"sqlite:///{fresh_path}", "fresh", engine_args={})
    db.create_all()
    try:
        db.engine.dispose()
    except Exception:
        pass


def dump_schema(path):
    """返回 {table: [(col_name, col_type, is_pk), ...]} 按声明顺序。"""
    con = sqlite3.connect(path)
    tables = {}
    for (t,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall():
        cols = [
            (r[1], r[2], r[5])
            for r in con.execute(f'PRAGMA table_info("{t}")').fetchall()
        ]
        tables[t] = cols
    con.close()
    return tables


def _preview(x, width=50):
    if x is None:
        return "NULL"
    s = str(x)
    return (s[:width] + "..") if len(s) > width else s


def _is_schema_row(sample):
    """判断 lost_and_found 一行是否是 sqlite_master 的 schema 碎片(c0=type,c4=CREATE)。"""
    if len(sample) >= 5 and sample[0] in SCHEMA_TYPES:
        c4 = sample[4]
        if isinstance(c4, str) and c4.lstrip().upper().startswith("CREATE"):
            return True
    return False


def get_laf_groups(path):
    """返回 [{rootpgno, max_nfield, count, sample}] 按 rootpgno 聚合。"""
    con = sqlite3.connect(path)
    colinfo = con.execute("PRAGMA table_info(lost_and_found)").fetchall()
    ccols = [r[1] for r in colinfo if r[1].startswith("c")]
    ccols.sort(key=lambda x: int(x[1:]))
    ccols = ccols[:10]
    collist = ",".join(ccols) if ccols else "NULL"
    groups = con.execute(
        "SELECT rootpgno, max(nfield), count(*) FROM lost_and_found GROUP BY rootpgno ORDER BY rootpgno"
    ).fetchall()
    result = []
    for rootpgno, max_nf, cnt in groups:
        sample = con.execute(
            f"SELECT {collist} FROM lost_and_found WHERE rootpgno=? LIMIT 1", (rootpgno,)
        ).fetchone()
        result.append(
            {
                "rootpgno": rootpgno,
                "max_nfield": max_nf,
                "count": cnt,
                "sample": list(sample) if sample else [],
            }
        )
    con.close()
    return result


def find_ipk_pos(cols):
    """找 INTEGER PRIMARY KEY 列的位置(rowid 别名)。无则返回 None。"""
    for i, (name, typ, pk) in enumerate(cols):
        if pk and (typ or "").upper() == "INTEGER":
            return i
    return None


def build_sources(cols, ipk_pos):
    """为目标表各列生成 lost_and_found 的来源表达式(id 或 c{i})。"""
    srcs = []
    for i in range(len(cols)):
        if i == ipk_pos:
            srcs.append("id")
        else:
            srcs.append(f"c{i}")
    return srcs


def cmd_analyze(args):
    print(f"[1/3] create_all 生成空 schema -> {args.fresh}")
    create_fresh_schema(args.fresh)
    schema = dump_schema(args.fresh)
    print(f"      建出 {len(schema)} 张表")
    print(f"[2/3] 分析 lost_and_found -> {args.recovered}")
    groups = get_laf_groups(args.recovered)
    total = sum(g["count"] for g in groups)
    print(f"      {len(groups)} 个 rootpgno,共 {total} 行")
    print("[3/3] 按列数匹配 + 识别 schema 碎片")
    colcounts = {t: len(c) for t, c in schema.items()}

    print("\n" + "=" * 90)
    print("SCHEMA (fresh create_all):  表名 [列数] [列名...]")
    for t, cols in schema.items():
        print(f"  {t} [{len(cols)}] {[c[0] for c in cols]}")

    print("\n" + "=" * 90)
    print("LOST_AND_FOUND rootpgno 分析 + 匹配建议:")
    for g in groups:
        is_schema = _is_schema_row(g["sample"])
        if is_schema:
            print(f"\n  rootpgno={g['rootpgno']}  max_nfield={g['max_nfield']}  rows={g['count']}  [sqlite_master schema 碎片,重建跳过]")
            print(f"    样本: {[_preview(x, 60) for x in g['sample']]}")
            continue
        cands = sorted([t for t, c in colcounts.items() if c == g["max_nfield"]])
        near = sorted([t for t, c in colcounts.items() if abs(c - g["max_nfield"]) == 1])
        print(f"\n  rootpgno={g['rootpgno']}  max_nfield={g['max_nfield']}  rows={g['count']}")
        print(f"    精确匹配(列数==max_nfield): {cands or '无'}")
        print(f"    近似匹配(差1): {near or '无'}")
        print(f"    样本: {[_preview(x) for x in g['sample']]}")

    out = {
        "schema": {t: [list(c) for c in cols] for t, cols in schema.items()},
        "lost_and_found": groups,
    }
    jpath = os.path.join(os.path.dirname(os.path.abspath(args.fresh)), "reconstruct_analysis.json")
    with open(jpath, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 90)
    print(f"分析已存 JSON: {jpath}")


def _do_insert(con, table, cols, sources, rootpgno, dry_run):
    """执行 INSERT INTO table SELECT sources FROM lost_and_found WHERE rootpgno=?"""
    tgt = ",".join(f'"{c[0]}"' for c in cols)
    src = ",".join(sources)
    sql = f'INSERT INTO "{table}" ({tgt}) SELECT {src} FROM lost_and_found WHERE rootpgno={int(rootpgno)}'
    if dry_run:
        cnt = con.execute(f"SELECT count(*) FROM lost_and_found WHERE rootpgno={int(rootpgno)}").fetchone()[0]
        return cnt, sql
    cur = con.execute(sql)
    return cur.rowcount, sql


def cmd_load(args):
    schema = dump_schema(args.fresh)
    colcounts = {t: len(c) for t, c in schema.items()}
    groups = get_laf_groups(args.recovered)

    # 准备输出库:复制 fresh(空 schema) -> out
    for ext in ("", "-wal", "-shm"):
        p = args.out + ext
        if os.path.exists(p):
            os.remove(p)
    shutil.copy(args.fresh, args.out)
    con = sqlite3.connect(args.out)
    con.execute(f"ATTACH DATABASE '{args.recovered}' AS src")

    # 人工 mapping:内置 DEFAULT_MAPPING + --mapping 文件(后者覆盖前者)
    manual = dict(DEFAULT_MAPPING)
    if args.mapping and os.path.exists(args.mapping):
        with open(args.mapping) as f:
            manual.update({int(k): v for k, v in json.load(f).items()})

    print(f"开始灌数据 -> {args.out}" + (" (dry-run,不实际写入)" if args.dry_run else ""))
    total_inserted = 0
    auto_ok, skipped = [], []
    for g in groups:
        rpg = g["rootpgno"]
        if _is_schema_row(g["sample"]):
            continue  # schema 碎片跳过
        if rpg in manual:
            table = manual[rpg]["table"]
            sources = manual[rpg]["sources"]
            if table not in schema:
                skipped.append((rpg, g["count"], f"manual 表不存在: {table}"))
                continue
            cols = schema[table]
            if len(sources) != len(cols):
                skipped.append((rpg, g["count"], f"manual sources数({len(sources)})!=列数({len(cols)})"))
                continue
            n, _ = _do_insert(con, table, cols, sources, rpg, args.dry_run)
            total_inserted += n
            auto_ok.append((rpg, table, n))
            continue
        # 自动匹配:列数 == max_nfield 且唯一
        cands = [t for t, c in colcounts.items() if c == g["max_nfield"]]
        if len(cands) != 1:
            skipped.append((rpg, g["count"], f"无精确唯一匹配(候选:{cands or '无'})"))
            continue
        table = cands[0]
        cols = schema[table]
        ipk_pos = find_ipk_pos(cols)
        sources = build_sources(cols, ipk_pos)
        try:
            n, _ = _do_insert(con, table, cols, sources, rpg, args.dry_run)
            total_inserted += n
            auto_ok.append((rpg, table, n))
        except Exception as e:
            skipped.append((rpg, g["count"], f"插入失败: {e}"))

    if not args.dry_run:
        con.commit()

    print("\n" + "=" * 90)
    print(f"已灌入 {total_inserted} 行,涉及 {len(auto_ok)} 个 rootpgno:")
    for rpg, table, n in auto_ok:
        print(f"  rootpgno={rpg} -> {table}: {n} 行")
    if skipped:
        print("\n跳过(需人工 mapping 或可放弃):")
        for rpg, cnt, reason in skipped:
            print(f"  rootpgno={rpg}  {cnt}行  {reason}")
    total_laf = sum(g["count"] for g in groups)
    unloaded = total_laf - total_inserted
    print(f"\n总计 lost_and_found {total_laf} 行,已灌入 {total_inserted} 行,未灌入 {unloaded} 行"
          "(含 schema 碎片 + 跳过的冲突/无匹配)")

    if not args.dry_run:
        # 各表行数
        print("\n各表行数:")
        for t in schema:
            n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
            if n:
                print(f"  {t}: {n}")
        ic = con.execute("PRAGMA integrity_check;").fetchone()[0]
        print(f"\nintegrity_check: {ic}")
    con.close()
    print("\n若行数正常,把 out 替换为 derisk.db(记得先备份)即可。")


def main():
    ap = argparse.ArgumentParser(description="从 lost_and_found 重建 derisk.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="生成空 schema + 分析 lost_and_found + 匹配建议")
    a.add_argument("--recovered", required=True, help="recovered.db 路径(含 lost_and_found)")
    a.add_argument("--fresh", required=True, help="生成的空 schema 库路径")
    l = sub.add_parser("load", help="把 lost_and_found 数据灌回正确的表,产出可用库")
    l.add_argument("--fresh", required=True, help="空 schema 库(analyze 生成的)")
    l.add_argument("--recovered", required=True, help="recovered.db 路径")
    l.add_argument("--out", required=True, help="输出的重建库路径")
    l.add_argument("--mapping", help="可选 JSON: {rootpgno: {table, sources[]}} 覆盖自动匹配")
    l.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = ap.parse_args()
    if args.cmd == "analyze":
        cmd_analyze(args)
    elif args.cmd == "load":
        cmd_load(args)


if __name__ == "__main__":
    main()
