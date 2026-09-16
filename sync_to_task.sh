#!/usr/bin/env bash
# 把仓库里的源码 / 测试 / 文档同步到验收副本（D:\0-task\rollingplan）
#
# 用法：
#   bash sync_to_task.sh            # 同步 + 逐个文件核对哈希
#   ROLLINGPLAN_TASK_DIR=/path bash sync_to_task.sh
#
# 只覆盖同名文件：*.py（源码 + 测试）、STATE.md、README.md、run_all_tests.sh。
# 不碰验收副本里的 .venv / build / dist / RollingPlan.spec（那些是构建产物）。
set -eu

ROOT="$(cd "$(dirname "$0")" && pwd)"
TASK_DIR="${ROLLINGPLAN_TASK_DIR:-/mnt/d/0-task/rollingplan}"

if [ ! -d "$TASK_DIR" ]; then
  echo "验收副本不存在：$TASK_DIR（可用 ROLLINGPLAN_TASK_DIR=/path 覆盖）" >&2
  exit 2
fi

copied=0
bad=0
for src in "$ROOT"/*.py "$ROOT"/STATE.md "$ROOT"/README.md "$ROOT"/run_all_tests.sh; do
  [ -f "$src" ] || continue
  name="$(basename "$src")"
  cp -f "$src" "$TASK_DIR/$name"
  a="$(git hash-object "$src")"
  b="$(git hash-object "$TASK_DIR/$name")"
  if [ "$a" = "$b" ]; then
    copied=$((copied + 1))
  else
    echo "哈希不一致：$name（$a != $b）" >&2
    bad=1
  fi
done

echo "已同步 $copied 个文件 → $TASK_DIR"
if [ "$bad" -ne 0 ]; then
  echo "有文件哈希不一致，检查是不是复制失败" >&2
  exit 1
fi
echo "跑测试：bash $TASK_DIR/run_all_tests.sh（或直接 bash $ROOT/run_all_tests.sh）"
