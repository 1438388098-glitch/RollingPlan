"""RollingPlan v0.30 数据防线回归测试（纯数据，零 UI 依赖，跑得最快）

防的坑（健壮性审计 P1-5，实机复现）：
- current_parent_idx = -5 通过 from_dict → current_parent 抛 IndexError，
  在导入校验放行 + PyQt5 槽内未捕获 = 进程直接 abort
- current_day = "3" 存活 → executor 里 start_date.addDays 抛 TypeError、
  重置确认框 f-string 抛 TypeError
"""

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rollingplan import PlanData, ParentPlan

PASS_COUNT = 0
FAIL_COUNT = 0


def ok(cond, label):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print("  PASS [%s]" % label)
    else:
        FAIL_COUNT += 1
        print("  FAIL [%s]" % label)


def parent_with(plans):
    p = ParentPlan("t")
    p.plans = plans
    p.time_slots = [{"name": "早", "count": 1}]
    p.normalize()
    return p


def test_parent_idx_sanitized():
    print("\n=== test_parent_idx_sanitized ===")
    for bad in (-5, -1, 1.5, "0", None, "abc"):
        d = PlanData()
        d.from_dict({"parents": [{"name": "A", "plans": [], "time_slots": []},
                                 {"name": "B", "plans": [], "time_slots": []}],
                     "current_parent_idx": bad})
        idx = d.current_parent_idx
        ok(isinstance(idx, int) and 0 <= idx < len(d.parents),
           "idx=%r → 合法下标 %r" % (bad, idx))
        try:
            _ = d.current_parent
            no_crash = True
        except Exception:
            no_crash = False
        ok(no_crash, "idx=%r → current_parent 可访问" % bad)


def test_parent_idx_normal_values_kept():
    print("\n=== test_parent_idx_normal_values_kept ===")
    d = PlanData()
    d.from_dict({"parents": [{"name": "A", "plans": [], "time_slots": []},
                             {"name": "B", "plans": [], "time_slots": []}],
                 "current_parent_idx": 1})
    ok(d.current_parent_idx == 1 and d.current_parent.name == "B",
       "合法 idx=1 原样保留")


def test_current_day_sanitized():
    print("\n=== test_current_day_sanitized ===")
    for bad in ("3", 2.7, -1, None, "abc"):
        p = parent_with(["a", "b"])
        p.from_dict({"name": "t", "plans": ["a", "b"], "time_slots": [{"name": "早", "count": 1}],
                     "start_date": "2026-01-01", "current_day": bad})
        day = p.current_day
        ok(isinstance(day, int) and day >= 0, "current_day=%r → 非负整数 %r" % (bad, day))
        try:
            d = p.start_date.addDays(day)
            ok(d.isValid(), "current_day=%r → addDays 可用 (%s)" % (bad, d.toString("yyyy-MM-dd")))
        except Exception as e:
            ok(False, "current_day=%r → addDays 崩了: %s" % (bad, e))


def test_sanitize_survives_full_pipeline():
    print("\n=== test_sanitize_survives_full_pipeline ===")
    d = PlanData()
    ok(d.from_dict({"parents": [{"name": "A", "plans": ["x"], "time_slots": [{"name": "早", "count": 1}]}],
                    "current_parent_idx": -9}) is None,
       "脏 idx 全管线 from_dict 不抛异常")
    p = d.current_parent
    ok(p.plans == ["x"], "数据本体不受防线影响")


def main():
    test_parent_idx_sanitized()
    test_parent_idx_normal_values_kept()
    test_current_day_sanitized()
    test_sanitize_survives_full_pipeline()

    print()
    print("PASS=%d  FAIL=%d" % (PASS_COUNT, FAIL_COUNT))
    if FAIL_COUNT == 0:
        print("=== ALL TESTS PASSED ===")
        sys.exit(0)
    else:
        print("=== TESTS FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
