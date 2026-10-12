"""考题二测试：正常用例 + 边界/异常用例。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app import storage
from app.main import app


@pytest.fixture()
def client(tmp_path):
    """每个测试用独立的临时 SQLite 库，互不污染。"""
    db = tmp_path / "test_ledger.db"
    storage.init_db(db)
    app.state.db = db
    # 通过依赖注入替换 DB_PATH（main 模块读取模块级变量）
    import app.main as main_mod
    original = main_mod.DB_PATH
    main_mod.DB_PATH = str(db)
    with TestClient(app) as c:
        yield c
    main_mod.DB_PATH = original


GOOD_RECORD = {"amount": 100.5, "type": "收入", "category": "工资", "date": "2026-10-01"}


# ---------- 正常用例 ----------

def test_post_record_success(client):
    """正常：新增收入流水，返回 201 + 完整记录（含 id）。"""
    resp = client.post("/records", json=GOOD_RECORD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] >= 1
    assert body["amount"] == 100.5
    assert body["type"] == "收入"


def test_get_records_filter_and_pagination(client):
    """正常：类型/分类/日期区间筛选 + 分页返回。"""
    # 准备 5 条数据：4 支出、1 收入
    client.post("/records", json={"amount": 10, "type": "支出", "category": "餐饮", "date": "2026-10-01"})
    client.post("/records", json={"amount": 20, "type": "支出", "category": "交通", "date": "2026-10-02"})
    client.post("/records", json={"amount": 30, "type": "支出", "category": "餐饮", "date": "2026-10-03"})
    client.post("/records", json={"amount": 500, "type": "收入", "category": "工资", "date": "2026-10-04"})
    client.post("/records", json={"amount": 25, "type": "支出", "category": "餐饮", "date": "2026-11-01"})

    # 类型筛选
    resp = client.get("/records", params={"type": "收入"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # 复合筛选：支出 + 餐饮 + 10 月区间（闭区间）
    resp = client.get("/records", params={
        "type": "支出", "category": "餐饮",
        "start_date": "2026-10-01", "end_date": "2026-10-31",
    })
    data = resp.json()
    assert data["total"] == 2  # 10-01 与 10-03 两条，11-01 被排除

    # 分页
    resp = client.get("/records", params={"page": 2, "page_size": 2})
    data = resp.json()
    assert data["total"] == 5
    assert data["page"] == 2
    assert len(data["records"]) == 2


def test_summary(client):
    """正常：区间汇总收入/支出/结余，且闭区间边界计入。"""
    client.post("/records", json={"amount": 1000, "type": "收入", "category": "工资", "date": "2026-10-01"})
    client.post("/records", json={"amount": 300, "type": "支出", "category": "餐饮", "date": "2026-10-15"})
    client.post("/records", json={"amount": 200, "type": "支出", "category": "交通", "date": "2026-10-31"})
    client.post("/records", json={"amount": 999, "type": "支出", "category": "餐饮", "date": "2026-11-01"})

    resp = client.get("/summary", params={"start_date": "2026-10-01", "end_date": "2026-10-31"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["income"] == 1000
    assert data["expense"] == 500
    assert data["balance"] == 500


def test_summary_empty_range(client):
    """边界：查询无任何数据的区间 -> 200 + 合计为 0，不报错。"""
    resp = client.get("/summary", params={"start_date": "2020-01-01", "end_date": "2020-12-31"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["income"] == 0 and data["expense"] == 0 and data["balance"] == 0


# ---------- 边界 / 异常用例 ----------

@pytest.mark.parametrize("payload,field", [
    ({"amount": 0, "type": "收入", "category": "工资", "date": "2026-10-01"}, "amount"),
    ({"amount": -5, "type": "收入", "category": "工资", "date": "2026-10-01"}, "amount"),
    ({"amount": 100, "type": "收支", "category": "工资", "date": "2026-10-01"}, "type"),
    ({"amount": 100, "type": "收入", "category": "", "date": "2026-10-01"}, "category"),
    ({"amount": 100, "type": "收入", "category": "工资", "date": "2026-02-30"}, "date"),
    ({"amount": 100, "type": "收入", "category": "工资", "date": "2026/01/01"}, "date"),
    ({"amount": "很多", "type": "收入", "category": "工资", "date": "2026-10-01"}, "amount"),
])
def test_post_invalid_records(client, payload, field):
    """异常：各类非法请求体 -> 400 + 结构化错误（含 code/message/field）。"""
    resp = client.post("/records", json=payload)
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert set(err) >= {"code", "message"}
    assert err.get("field") == field


def test_post_missing_body(client):
    """异常：缺字段请求体 -> 400 结构化错误。"""
    resp = client.post("/records", json={"amount": 100})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_get_records_invalid_filters(client):
    """异常：查询参数非法（type 错值、日期区间颠倒、page=0）-> 400。"""
    resp = client.get("/records", params={"type": "收支"})
    assert resp.status_code == 400

    resp = client.get("/records", params={"start_date": "2026-10-31", "end_date": "2026-10-01"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_DATE_RANGE"

    resp = client.get("/records", params={"page": 0})
    assert resp.status_code == 400

    resp = client.get("/records", params={"start_date": "2026-13-01"})
    assert resp.status_code == 400


def test_concurrent_writes(client):
    """并发写入：多线程并发 POST，全部成功且无数据丢失/损坏。"""
    import threading

    results = []
    lock = threading.Lock()

    def post(i):
        resp = client.post("/records", json={
            "amount": 10 + i, "type": "支出", "category": "并发测试", "date": "2026-10-05"
        })
        with lock:
            results.append(resp.status_code)

    threads = [threading.Thread(target=post, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(code == 201 for code in results)  # 20 个并发写全部成功
    resp = client.get("/records", params={"category": "并发测试", "page_size": 100})
    assert resp.json()["total"] == 20  # 无丢失
    ids = [r["id"] for r in resp.json()["records"]]
    assert len(set(ids)) == 20  # 无主键冲突
