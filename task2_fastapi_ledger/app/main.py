"""FastAPI 记账服务入口。

启动：uvicorn app.main:app --reload
接口：
  POST /records   新增流水（校验金额>0、类型合法、日期格式）
  GET  /records   按类型/分类/日期区间筛选 + 分页
  GET  /summary   区间收入合计 / 支出合计 / 结余
非法参数统一返回 4xx + 结构化错误信息 {"error": {...}}。
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from . import storage
from .models import (
    LedgerError,
    RecordCreate,
    RecordListOut,
    RecordOut,
    SummaryOut,
    check_date_range,
    parse_date_param,
)

DB_PATH = os.environ.get("LEDGER_DB") or None  # 测试注入临时库用


@asynccontextmanager
async def lifespan(application: FastAPI):
    storage.init_db(DB_PATH)
    yield


app = FastAPI(title="简易记账服务", version="1.0.0", lifespan=lifespan)


# ---------- 全局异常处理：统一结构化 4xx 错误 ----------

@app.exception_handler(LedgerError)
async def ledger_error_handler(request: Request, exc: LedgerError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": exc.code, "message": exc.message, "field": exc.field}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """把 FastAPI 默认 422 转成 400 + 统一错误结构。"""
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": first.get("msg", "请求参数校验失败"),
                "field": loc or None,
                "details": [
                    {"field": ".".join(str(x) for x in e.get("loc", []) if x != "body"),
                     "message": e.get("msg", "")}
                    for e in errors
                ],
            }
        },
    )


# ---------- 接口 ----------

class QueryParams(BaseModel):
    """GET /records 查询参数校验。"""
    type: str | None = None
    category: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    page: int = 1
    page_size: int = 20

    @field_validator("type")
    @classmethod
    def check_type(cls, v):
        if v is not None and v not in ("收入", "支出"):
            raise LedgerError("INVALID_TYPE", "type 必须是 收入 或 支出", "type")
        return v

    @field_validator("page", "page_size")
    @classmethod
    def check_positive(cls, v, info):
        if v < 1:
            raise LedgerError("INVALID_PAGINATION", f"{info.field_name} 必须 >= 1", info.field_name)
        return v

    @field_validator("page_size")
    @classmethod
    def check_page_size_cap(cls, v):
        if v > 100:
            raise LedgerError("INVALID_PAGINATION", "page_size 上限为 100", "page_size")
        return v


@app.post("/records", response_model=RecordOut, status_code=201)
def create_record(body: RecordCreate):
    rid = storage.insert_record(
        body.amount, body.type, body.category, body.date, DB_PATH
    )
    return RecordOut(id=rid, amount=body.amount, type=body.type,
                     category=body.category, date=body.date)


@app.get("/records", response_model=RecordListOut)
def list_records(
    type: str | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    params = QueryParams(type=type, category=category, start_date=start_date,
                         end_date=end_date, page=page, page_size=page_size)

    start = parse_date_param(params.start_date, "start_date") if params.start_date else None
    end = parse_date_param(params.end_date, "end_date") if params.end_date else None
    check_date_range(start, end)

    total, records = storage.query_records(
        rtype=params.type, category=params.category,
        start=params.start_date, end=params.end_date,
        page=params.page, page_size=params.page_size, db_path=DB_PATH,
    )
    return RecordListOut(total=total, page=params.page, page_size=params.page_size,
                         records=[RecordOut(**r) for r in records])


@app.get("/summary", response_model=SummaryOut)
def get_summary(start_date: str | None = None, end_date: str | None = None):
    start = parse_date_param(start_date, "start_date") if start_date else None
    end = parse_date_param(end_date, "end_date") if end_date else None
    check_date_range(start, end)

    result = storage.summary(start_date, end_date, DB_PATH)
    return SummaryOut(start_date=start_date, end_date=end_date, **result)
