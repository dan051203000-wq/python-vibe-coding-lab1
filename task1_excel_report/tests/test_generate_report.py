"""考题一测试：正常用例 + 边界/异常用例。"""
from pathlib import Path

import pandas as pd
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_report import (
    REQUIRED_COLUMNS,
    ReportError,
    generate,
)

COLUMNS = ["日期", "销售员", "产品", "数量", "单价", "地区"]
assert REQUIRED_COLUMNS == COLUMNS  # 脚本要求的 6 列与测试约定一致


def make_xlsx(tmp_path: Path, rows, name="sales_raw.xlsx", columns=COLUMNS) -> Path:
    p = tmp_path / name
    pd.DataFrame(rows, columns=columns).to_excel(p, index=False)
    return p


GOOD_ROWS = [
    ("2026-10-01", "张三", "键盘", 3, 100.0, "华东"),
    ("2026-10-02", "李四", "鼠标", 2, 50.0, "华南"),
    ("2026-10-02", "张三", "键盘", 1, 100.0, "华东"),
]


# ---------- 正常用例 ----------

def test_normal_report(tmp_path):
    """正常数据：一键生成 4 个工作表，统计数值正确。"""
    src = make_xlsx(tmp_path, GOOD_ROWS)
    out = tmp_path / "report.xlsx"
    sheets = generate(src, out)
    assert out.exists()
    assert set(sheets.keys()) == {"明细清洗后", "按销售员", "按地区", "总览"}
    # 张三：3*100 + 1*100 = 400；李四：2*50 = 100
    by_sales = sheets["按销售员"].set_index("销售员")["销售额"]
    assert by_sales["张三"] == pytest.approx(400.0)
    assert by_sales["李四"] == pytest.approx(100.0)
    # 华东 400，华南 100
    by_region = sheets["按地区"].set_index("地区")["销售额"]
    assert by_region["华东"] == pytest.approx(400.0)
    assert by_region["华南"] == pytest.approx(100.0)
    # 月度总额 = 500
    total = sheets["总览"].set_index("指标")["数值"]["月度销售总额"]
    assert total == pytest.approx(500.0)


def test_cleaning_rules(tmp_path):
    """清洗规则：空值行、数量<=0、重复行全部剔除，且只保留第一条。"""
    rows = GOOD_ROWS + [
        (None, "张三", "键盘", 3, 100.0, "华东"),   # 空值行
        ("2026-10-02", "李四", "鼠标", 0, 50.0, "华南"),   # 数量=0
        ("2026-10-03", "李四", "鼠标", -2, 50.0, "华南"),  # 数量为负
        ("2026-10-01", "张三", "键盘", 3, 100.0, "华东"),  # 完全重复
    ]
    src = make_xlsx(tmp_path, rows)
    out = tmp_path / "report.xlsx"
    sheets = generate(src, out)
    assert len(sheets["明细清洗后"]) == 3  # 只剩 3 行有效数据
    assert float(sheets["总览"].set_index("指标")["数值"]["月度销售总额"]) == pytest.approx(500.0)


def test_original_file_untouched(tmp_path):
    """约束验证：原始文件字节级不变（md5 前后一致）。"""
    import hashlib

    src = make_xlsx(tmp_path, GOOD_ROWS)
    md5_before = hashlib.md5(src.read_bytes()).hexdigest()
    generate(src, tmp_path / "report.xlsx")
    md5_after = hashlib.md5(src.read_bytes()).hexdigest()
    assert md5_before == md5_after


# ---------- 边界 / 异常用例 ----------

def test_file_not_exist(tmp_path):
    """异常：输入文件不存在 -> 明确报错、不崩溃。"""
    with pytest.raises(ReportError, match="不存在"):
        generate(tmp_path / "no_such.xlsx", tmp_path / "report.xlsx")


def test_missing_columns(tmp_path):
    """异常：缺少必需列 -> 明确列出缺失列名。"""
    p = tmp_path / "bad_cols.xlsx"
    pd.DataFrame([{"日期": "2026-10-01", "销售员": "张三"}]).to_excel(p, index=False)
    with pytest.raises(ReportError, match="缺少必需列.*地区"):
        generate(p, tmp_path / "report.xlsx")


def test_empty_file(tmp_path):
    """异常：空文件（无数据行）-> 明确报错。"""
    p = tmp_path / "empty.xlsx"
    pd.DataFrame(columns=COLUMNS).to_excel(p, index=False)
    with pytest.raises(ReportError, match="无有效数据|空"):
        generate(p, tmp_path / "report.xlsx")


def test_all_dirty_data(tmp_path):
    """边界：全部行均为脏数据 -> 清洗后 0 行，给出明确提示而非错误报表。"""
    rows = [
        (None, "张三", "键盘", 3, 100.0, "华东"),
        ("2026-10-01", "李四", "鼠标", -1, 50.0, "华南"),
        ("2026-10-01", "李四", "鼠标", 0, 50.0, "华南"),
    ]
    src = make_xlsx(tmp_path, rows)
    with pytest.raises(ReportError, match="清洗后无有效数据"):
        generate(src, tmp_path / "report.xlsx")


def test_output_same_as_input_rejected(tmp_path):
    """约束验证：输出路径 = 输入路径时拒绝执行（保护原始文件）。"""
    src = make_xlsx(tmp_path, GOOD_ROWS)
    with pytest.raises(ReportError, match="不能与输入文件相同"):
        generate(src, src)


def test_not_excel_file(tmp_path):
    """异常：文件存在但不是合法 Excel -> 明确报错、不崩溃。"""
    p = tmp_path / "fake.xlsx"
    p.write_text("this is not an excel file", encoding="utf-8")
    with pytest.raises(ReportError, match="无法读取"):
        generate(p, tmp_path / "report.xlsx")
