"""考题一：Excel 报表生成脚本。

读取 sales_raw.xlsx，完成数据清洗与统计，输出 report.xlsx。
- 清洗：删除关键字段缺失的行、剔除数量<=0 的行、按全字段去重
- 统计：按销售员 / 按地区汇总销售额，并给出月度总额
- 输出：明细清洗后 / 按销售员 / 按地区 / 总览 四个工作表
- 约束：只读打开原始文件，绝不修改；异常输入给出明确报错
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["日期", "销售员", "产品", "数量", "单价", "地区"]


class ReportError(Exception):
    """业务异常：携带可直接展示给用户的可读错误信息。"""


def file_md5(path: str | Path) -> str:
    """计算文件 md5，用于验证原始文件未被修改。"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_raw(path: str | Path) -> pd.DataFrame:
    """读取并校验原始 Excel 文件，返回 DataFrame。"""
    path = Path(path)
    if not path.exists():
        raise ReportError(f"输入文件不存在：{path.resolve()}")

    try:
        df = pd.read_excel(path)
    except Exception as exc:  # 空文件 / 非 Excel 格式等
        raise ReportError(
            f"无法读取 Excel 文件（可能为空文件或格式非法）：{path}，原因：{exc}"
        ) from exc

    if df.shape[0] == 0 or df.shape[1] == 0:
        raise ReportError(f"文件为空（无数据行）：{path}")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ReportError(
            f"缺少必需列：{missing}；文件实际包含列：{list(df.columns)}"
        )
    return df


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """执行清洗规则，返回（清洗后 DataFrame, 清洗统计信息）。"""
    stats = {"原始行数": len(df)}

    # 1. 删除关键字段缺失的行（6 个字段全部为关键字段）
    df = df.dropna(subset=REQUIRED_COLUMNS)
    n1 = len(df)

    # 2. 数量/单价转数值；剔除数量<=0 的异常行（非数值行同样无法统计，一并剔除）
    df["数量"] = pd.to_numeric(df["数量"], errors="coerce")
    df["单价"] = pd.to_numeric(df["单价"], errors="coerce")
    df = df.dropna(subset=["数量", "单价"])
    df = df[df["数量"] > 0]
    n2 = len(df)

    # 3. 按全字段去重，保留第一条
    df = df.drop_duplicates(subset=REQUIRED_COLUMNS, keep="first")

    stats["删除空值行"] = stats["原始行数"] - n1
    stats["剔除数量异常行"] = n1 - n2
    stats["删除重复行"] = n2 - len(df)
    stats["清洗后行数"] = len(df)
    return df, stats


def build_report(df_clean: pd.DataFrame, raw_count: int, dropped: int) -> dict[str, pd.DataFrame]:
    """基于清洗后数据构建 4 个工作表。"""
    if df_clean.empty:
        raise ReportError(
            f"清洗后无有效数据（原始 {raw_count} 行，共剔除 {dropped} 行），不生成报表。"
            "请检查数据源：可能全部行存在空值/重复/非正数量问题。"
        )

    detail = df_clean.copy()
    detail["销售额"] = detail["数量"] * detail["单价"]

    by_sales = (
        detail.groupby("销售员", as_index=False)["销售额"].sum().sort_values("销售额", ascending=False)
    )
    by_region = (
        detail.groupby("地区", as_index=False)["销售额"].sum().sort_values("销售额", ascending=False)
    )
    overview = pd.DataFrame(
        {
            "指标": [
                "月度销售总额",
                "原始数据行数",
                "清洗后数据行数",
                "被剔除行数",
                "参与销售员人数",
                "覆盖地区数",
            ],
            "数值": [
                round(float(detail["销售额"].sum()), 2),
                raw_count,
                len(detail),
                dropped,
                detail["销售员"].nunique(),
                detail["地区"].nunique(),
            ],
        }
    )
    return {
        "明细清洗后": detail,
        "按销售员": by_sales,
        "按地区": by_region,
        "总览": overview,
    }


def generate(input_path: str | Path, output_path: str | Path) -> dict[str, pd.DataFrame]:
    """主流程：读取 -> 清洗 -> 统计 -> 写出 report.xlsx。"""
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ReportError("输出文件不能与输入文件相同（约束：不得修改原始文件）。")

    df = load_raw(input_path)  # 内部先做存在性/格式/列校验
    md5_before = file_md5(input_path)
    raw_count = len(df)

    df_clean, _stats = clean(df)
    dropped = raw_count - len(df_clean)
    sheets = build_report(df_clean, raw_count, dropped)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, sheet_df in sheets.items():
            sheet_df.to_excel(writer, sheet_name=name, index=False)

    if file_md5(input_path) != md5_before:
        raise ReportError("严重错误：原始文件被修改，请立即检查代码！")
    return sheets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="销售数据清洗与报表生成")
    parser.add_argument("--input", "-i", default="sales_raw.xlsx", help="原始数据文件路径")
    parser.add_argument("--output", "-o", default="report.xlsx", help="输出报表路径")
    args = parser.parse_args(argv)

    try:
        sheets = generate(args.input, args.output)
    except ReportError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1

    overview = sheets["总览"]
    print(f"[成功] 报表已生成：{Path(args.output).resolve()}")
    print(overview.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
