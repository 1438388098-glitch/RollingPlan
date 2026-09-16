#!/usr/bin/env bash
# RollingPlan 全套 headless 测试（仓库版；验收副本里也是同一份）
#
# 用法：
#   bash run_all_tests.sh                                   # 自动挑一个带 PyQt5 的 python
#   ROLLINGPLAN_PYTHON=/path/to/python bash run_all_tests.sh
#
# 退出码：0 = 全部测试通过；1 = 有测试失败；2 = 环境问题（找不到 python / 没有 PyQt5）
# 每个测试文件的完整输出在 $LOG_DIR/rollingplan-test-<文件名>.log（默认 /tmp）
#
# 历史坑（2026-09-16 修）：老版把每个测试的输出 pipe 给 tail —— 管道退出码是
# 最后一段命令的（tail 恒为 0），于是**测试全挂也报「全过」**。现在改成写日志文件 +
# 用 python 自己的退出码判断，脚本自己 exit 非零。
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
TASK_DIR="${ROLLINGPLAN_TASK_DIR:-/mnt/d/0-task/rollingplan}"
LOG_DIR="${ROLLINGPLAN_LOG_DIR:-${TMPDIR:-/tmp}}"

TEST_FILES="
test_v2_2.py
test_import_export_v04.py
test_reset_v04.py
test_theme_v05.py
test_minimal_v06.py
test_scroll_v11.py
test_regression_v13.py
test_undo_v16.py
test_calendar_v18.py
test_note_v19.py
test_keyboard_v20.py
test_tabs_v30.py
test_import_cancel_v30.py
test_data_sanity_v30.py
test_page_sync_v30.py
test_data_safety_v30.py
"

# ---- 挑解释器：环境变量 > 本目录 venv > 验收副本 venv > 系统 python ----
PY_BIN=""
for cand in "${ROLLINGPLAN_PYTHON:-}" "$ROOT/.venv/bin/python" "$TASK_DIR/.venv/bin/python" \
            "$(command -v python3 2>/dev/null || true)" "$(command -v python 2>/dev/null || true)"; do
  if [ -n "$cand" ] && [ -x "$cand" ]; then
    PY_BIN="$cand"
    break
  fi
done
if [ -z "$PY_BIN" ]; then
  echo "找不到 python 解释器（可用 ROLLINGPLAN_PYTHON=/path/to/python 指定）" >&2
  exit 2
fi
if ! "$PY_BIN" -c "import PyQt5" >/dev/null 2>&1; then
  echo "这个解释器里没有 PyQt5：$PY_BIN" >&2
  echo "试试：ROLLINGPLAN_PYTHON=$TASK_DIR/.venv/bin/python bash run_all_tests.sh" >&2
  exit 2
fi

echo "python: $PY_BIN"
export QT_QPA_PLATFORM=offscreen
cd "$ROOT"

fail=0
for f in $TEST_FILES; do
  if [ ! -f "$f" ]; then
    echo "=== $f === 缺失（跳过）"
    continue
  fi
  echo "=== $f ==="
  log="$LOG_DIR/rollingplan-test-$f.log"
  if "$PY_BIN" "$f" >"$log" 2>&1; then
    tail -2 "$log"
  else
    echo "FAIL: $f （完整输出 $log）"
    tail -25 "$log"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "全部通过（16 个测试文件）"
else
  echo "有测试失败 —— 别提交" >&2
fi
exit $fail
