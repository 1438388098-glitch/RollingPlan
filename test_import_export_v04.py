"""
RollingPlan v0.4 导入/导出测试

覆盖：
- export_to_dict：含 version/exported_at/data 三段
- export_to_file / import_from_file round-trip：字段一致
- 导入空 PlanData（边界）
- 校验失败：JSON 语法错 / 根非 dict / 缺字段 / parents 空 / plans 非字符串 / 版本不匹配
- 借用进度（borrowed_slots）round-trip 保留

运行：QT_QPA_PLATFORM=offscreen python test_import_export_v04.py
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

from PyQt5.QtCore import QDate
from rollingplan import PlanData, PlanScheduler, ParentPlan


PASS_COUNT = 0
FAIL_COUNT = 0


def assert_eq(actual, expected, label):
    global PASS_COUNT, FAIL_COUNT
    if actual == expected:
        PASS_COUNT += 1
        print(f"  PASS [{label}]")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL [{label}]")
        print(f"    expected: {expected!r}")
        print(f"    actual:   {actual!r}")
        sys.exit(1)


def assert_true(cond, label):
    global PASS_COUNT, FAIL_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS [{label}]")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL [{label}]")
        sys.exit(1)


# ============== 测试 ==============

def make_rich_data():
    """构造一个丰富 PlanData：2 分类 + 借用进度"""
    pd = PlanData()

    # 分类 1：工作 — 6 plans + 早×1晚×2 = 3 slots/day → 2 天
    # current=0 时 future = day1 (3 个槽位可借)
    p1 = ParentPlan("工作")
    p1.time_slots = [{"name": "早", "count": 1}, {"name": "晚", "count": 2}]
    p1.plans = ["写报告", "开会", "回邮件", "review", "提交周报", "归档"]
    p1.start_date = QDate(2026, 9, 15)
    p1.current_day = 0
    s1 = PlanScheduler(p1)
    s1.borrow_slot("早")  # 借 day1 早
    s1.borrow_slot("晚")  # 借 day1 晚
    pd.parents[0] = p1

    # 分类 2：健身 — 3 plans + 上午×1 = 1 slot/day → 3 天
    # current=0 时 future = day1, day2（2 个槽位可借）
    pd.add_parent("健身")
    p2 = pd.parents[1]
    p2.time_slots = [{"name": "上午", "count": 1}]
    p2.plans = ["跑步30分钟", "拉伸", "力量训练"]
    p2.start_date = QDate(2026, 9, 15)
    p2.current_day = 0
    s2 = PlanScheduler(p2)
    s2.borrow_slot("上午")  # 借 day1 上午

    pd.current_parent_idx = 1  # 当前在「健身」
    return pd


def test_export_to_dict_structure():
    print("\n=== test_export_to_dict_structure ===")
    pd = make_rich_data()
    payload = pd.export_to_dict()

    assert_eq(set(payload.keys()), {"version", "exported_at", "data"}, "payload 顶层三键")
    assert_eq(payload["version"], "0.4", "version=0.4")
    assert_true(isinstance(payload["exported_at"], str) and len(payload["exported_at"]) >= 10,
                "exported_at 是 ISO 字符串")
    assert_true(isinstance(payload["data"], dict), "data 是 dict")
    assert_eq(len(payload["data"]["parents"]), 2, "data 含 2 个分类")


def test_round_trip_full():
    print("\n=== test_round_trip_full: 导出 → 读回 → 字段一致 ===")
    pd = make_rich_data()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "backup.json"
        ok, msg = pd.export_to_file(str(path))
        assert_eq(ok, True, "导出成功")

        # 模拟「新设备」：从空 PlanData 开始
        pd2 = PlanData()
        ok, msg, stats = pd2.import_from_file(str(path))
        assert_eq(ok, True, "导入成功")
        assert_eq(stats["parents"], 2, "stats parents=2")
        assert_eq(stats["plans_total"], 9, "stats plans_total=9 (6+3)")
        # 工作 2 个 + 健身 1 个
        assert_eq(stats["borrowed_total"], 3, "stats borrowed_total=3")

        # 字段对比
        assert_eq(len(pd2.parents), 2, "2 分类")
        assert_eq(pd2.parents[0].name, "工作", "分类 0 名")
        assert_eq(pd2.parents[1].name, "健身", "分类 1 名")
        assert_eq(pd2.parents[0].plans, ["写报告", "开会", "回邮件", "review", "提交周报", "归档"], "工作 plans")
        assert_eq(pd2.parents[0].time_slots, [{"name": "早", "count": 1}, {"name": "晚", "count": 2}], "工作 time_slots")
        assert_eq(pd2.parents[0].current_day, 0, "工作 current_day")
        assert_eq(pd2.parents[0].borrowed_slots,
                  pd.parents[0].borrowed_slots, "工作 borrowed 一致")
        assert_eq(pd2.parents[1].borrowed_slots,
                  pd.parents[1].borrowed_slots, "健身 borrowed 一致")
        assert_eq(pd2.current_parent_idx, 1, "current_parent_idx 跟随")


def test_round_trip_empty():
    print("\n=== test_round_trip_empty: 空 PlanData 也能导出/导入 ===")
    pd = PlanData()
    # 默认 1 个空分类（plans=[] time_slots=[]）
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "empty.json"
        ok, _ = pd.export_to_file(str(path))
        assert_eq(ok, True, "空数据导出成功")

        pd2 = PlanData()
        ok, _, stats = pd2.import_from_file(str(path))
        assert_eq(ok, True, "空数据导入成功")
        assert_eq(stats["parents"], 1, "stats parents=1")
        assert_eq(stats["plans_total"], 0, "stats plans_total=0")
        assert_eq(stats["borrowed_total"], 0, "stats borrowed_total=0")


def test_import_file_not_found():
    print("\n=== test_import_file_not_found ===")
    pd = PlanData()
    ok, msg, stats = pd.import_from_file("/nonexistent/path/never.json")
    assert_eq(ok, False, "失败")
    assert_eq(stats, None, "stats=None")
    assert_true("不存在" in msg, f"错误信息提到「不存在」: {msg!r}")


def test_import_invalid_json():
    print("\n=== test_import_invalid_json: JSON 语法错 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "bad.json"
        path.write_text("{ this is not json", encoding="utf-8")
        pd = PlanData()
        ok, msg, stats = pd.import_from_file(str(path))
        assert_eq(ok, False, "失败")
        assert_eq(stats, None, "stats=None")
        assert_true("JSON 解析失败" in msg, f"错误信息: {msg!r}")


def test_import_root_not_dict():
    print("\n=== test_import_root_not_dict ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "list.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        pd = PlanData()
        ok, msg, _ = pd.import_from_file(str(path))
        assert_eq(ok, False, "失败")
        assert_true("根必须是 JSON 对象" in msg, f"错误信息: {msg!r}")


def test_import_parents_missing():
    print("\n=== test_import_parents_missing: 缺 parents 字段 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "no_parents.json"
        path.write_text(json.dumps({"version": "0.4", "data": {"foo": "bar"}}),
                        encoding="utf-8")
        pd = PlanData()
        ok, msg, _ = pd.import_from_file(str(path))
        assert_eq(ok, False, "失败")
        assert_true("parents" in msg, f"错误信息: {msg!r}")


def test_import_parents_empty():
    print("\n=== test_import_parents_empty: parents 为空数组 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "empty_parents.json"
        path.write_text(json.dumps({"version": "0.4", "data": {"parents": []}}),
                        encoding="utf-8")
        pd = PlanData()
        ok, msg, _ = pd.import_from_file(str(path))
        assert_eq(ok, False, "失败")
        assert_true("不能为空" in msg, f"错误信息: {msg!r}")


def test_import_parent_missing_field():
    print("\n=== test_import_parent_missing_field: 单个 parent 缺字段 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "missing_field.json"
        path.write_text(json.dumps({
            "version": "0.4",
            "data": {"parents": [{"name": "X", "plans": []}]},  # 缺 time_slots
        }), encoding="utf-8")
        pd = PlanData()
        ok, msg, _ = pd.import_from_file(str(path))
        assert_eq(ok, False, "失败")
        assert_true("time_slots" in msg, f"错误信息: {msg!r}")


def test_import_plans_not_string():
    print("\n=== test_import_plans_not_string: plans 内有非字符串 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "bad_plan.json"
        path.write_text(json.dumps({
            "version": "0.4",
            "data": {"parents": [{
                "name": "X", "plans": ["valid", 123], "time_slots": [],
            }]},
        }), encoding="utf-8")
        pd = PlanData()
        ok, msg, _ = pd.import_from_file(str(path))
        assert_eq(ok, False, "失败")
        assert_true("不是字符串" in msg, f"错误信息: {msg!r}")


def test_import_version_mismatch():
    print("\n=== test_import_version_mismatch: 版本不兼容 ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "old_version.json"
        path.write_text(json.dumps({
            "version": "0.3",  # 旧版本
            "data": {"parents": [{"name": "X", "plans": [], "time_slots": []}]},
        }), encoding="utf-8")
        pd = PlanData()
        ok, msg, _ = pd.import_from_file(str(path))
        assert_eq(ok, False, "失败")
        assert_true("版本不兼容" in msg, f"错误信息: {msg!r}")


def test_import_legacy_no_wrapper():
    print("\n=== test_import_legacy_no_wrapper: 旧格式无 wrapper ===")
    """无 version/exported_at/data wrapper 的纯 to_dict() 输出也应能导入"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "legacy.json"
        path.write_text(json.dumps({
            "parents": [{
                "name": "legacy-cat",
                "plans": ["老计划"],
                "time_slots": [{"name": "早", "count": 1}],
                "start_date": "2026-09-15",
                "current_day": 0,
                "borrowed_slots": [],
            }],
            "current_parent_idx": 0,
        }, ensure_ascii=False), encoding="utf-8")
        pd = PlanData()
        ok, msg, stats = pd.import_from_file(str(path))
        assert_eq(ok, True, "旧格式导入成功")
        assert_eq(stats["parents"], 1, "stats parents=1")
        assert_eq(pd.parents[0].name, "legacy-cat", "分类名保留")


def test_import_undo_on_cancel():
    """用户取消确认时不应污染当前数据（手动模拟）"""
    print("\n=== test_import_undo_on_cancel: 取消时回滚 ===")
    pd = make_rich_data()
    # 备份当前状态
    orig_names = [p.name for p in pd.parents]
    orig_borrowed = [list(p.borrowed_slots) for p in pd.parents]

    # 模拟校验成功但用户取消——UI 层会调用 data.load() 重新加载磁盘
    # 这里直接验证 data.load() 能恢复原状
    pd.save()  # 把当前状态写盘
    # 修改内存（模拟 import 做了 from_dict）
    pd.parents[0].name = "TAMPERED"
    assert_eq(pd.parents[0].name, "TAMPERED", "内存已被改")
    # 回滚
    ok = pd.load()
    assert_eq(ok, True, "load 成功")
    assert_eq(pd.parents[0].name, orig_names[0], "回滚后名字恢复")
    assert_eq(pd.parents[0].borrowed_slots, orig_borrowed[0], "回滚后借用恢复")


# ============== 入口 ==============

def main():
    test_export_to_dict_structure()
    test_round_trip_full()
    test_round_trip_empty()
    test_import_file_not_found()
    test_import_invalid_json()
    test_import_root_not_dict()
    test_import_parents_missing()
    test_import_parents_empty()
    test_import_parent_missing_field()
    test_import_plans_not_string()
    test_import_version_mismatch()
    test_import_legacy_no_wrapper()
    test_import_undo_on_cancel()
    print(f"\n=== ALL TESTS PASSED ({PASS_COUNT} assertions) ===")


if __name__ == "__main__":
    main()
