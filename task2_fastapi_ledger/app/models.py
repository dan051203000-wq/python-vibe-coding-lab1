"""考题二数据模型与校验规则。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator

RecordType = Literal["收入", "支出"]

VALID_TYPES = ("收入", "支出")


class LedgerError(Exception):
    """业务校验错误：携带结构化字段信息，由全局异常处理器转为 4xx 响应。"""

    def __init__(self, code: str, message: str, field: str | None = None):
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)


class RecordCreate(BaseModel):
    """POST /records 请求体。"""
    amount: float
    type: str
    category: str
    date: str  # YYYY-MM-DD

    @field_validator("amount")
    @classmethod
    def check_amount(cls, v: float) -> float:
        if v <= 0:
            raise LedgerError("INVALID_AMOUNT", "金额必须大于 0", "amount")
        if v != v or v in (float("inf"), float("-inf")):  # NaN / Inf
            raise LedgerError("INVALID_AMOUNT", "金额必须为有限数值", "amount")
        return v

    @field_validator("type")
    @classmethod
    def check_type(cls, v: str) -> str:
        if v not in VALID_TYPES:
            raise LedgerError(
                "INVALID_TYPE", f"类型必须是 {' 或 '.join(VALID_TYPES)}，收到：{v!r}", "type"
            )
        return v

    @field_validator("category")
    @classmethod
    def check_category(cls, v: str) -> str:
        if not v or not v.strip():
            raise LedgerError("INVALID_CATEGORY", "分类不能为空", "category")
        return v.strip()

    @field_validator("date")
    @classmethod
    def check_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise LedgerError(
                "INVALID_DATE", "日期必须为 YYYY-MM-DD 格式的合法日历日期，如 2026-10-01", "date"
            )
        return v


class RecordOut(BaseModel):
    """GET /records 单条记录。"""
    id: int
    amount: float
    type: str
    category: str
    date: str


class RecordListOut(BaseModel):
    """GET /records 分页响应。"""
    total: int
    page: int
    page_size: int
    records: list[RecordOut]


class SummaryOut(BaseModel):
    """GET /summary 响应。"""
    start_date: str | None = None
    end_date: str | None = None
    income: float
    expense: float
    balance: float


def parse_date_param(value: str, field: str) -> date:
    """解析查询参数中的日期，非法则抛结构化错误。"""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise LedgerError("INVALID_DATE", f"{field} 必须为 YYYY-MM-DD 格式，收到：{value!r}", field)


def check_date_range(start: date | None, end: date | None) -> None:
    if start and end and start > end:
        raise LedgerError(
            "INVALID_DATE_RANGE", "start_date 不能晚于 end_date", "start_date"
        )
