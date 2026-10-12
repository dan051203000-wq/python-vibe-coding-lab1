# Python Vibe Coding — Lab 1

用自然语言驱动 AI 编码助手完成的 Python 工程作业，包含两道实操考题的完整交付物：
需求澄清清单、可运行源代码、测试用例（正常 + 边界/异常）、AI 协作过程记录与复盘。

## 目录结构

```
python-vibe-coding-lab1/
├── README.md                    # 本文件：运行说明
├── requirements.txt             # 依赖清单
├── .gitignore
├── docs/
│   ├── 01_需求澄清清单.md        # 交给 AI 之前先写清目标/输入输出/边界/验收标准
│   ├── 02_AI协作过程记录.md      # 关键对话摘要 + 代码修改轨迹
│   └── 03_复盘.md               # 哪些交给 AI、哪些自己拍板、哪些风险人工审查
├── task1_excel_report/          # 考题一：Excel 报表生成脚本（必做，40 分）
│   ├── generate_report.py       # 主脚本：清洗 + 统计 + 输出 report.xlsx
│   ├── make_sample_data.py      # 生成含脏数据的样例 sales_raw.xlsx
│   └── tests/
│       └── test_generate_report.py
└── task2_fastapi_ledger/        # 考题二：FastAPI 记账接口
    ├── app/
    │   ├── __init__.py
    │   ├── main.py              # FastAPI 应用与路由
    │   ├── models.py            # Pydantic 数据模型与校验
    │   └── storage.py           # SQLite 存储层（WAL + 事务）
    └── tests/
        └── test_api.py
```

## 环境准备

要求 Python 3.10+，然后：

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

---

## 考题一：Excel 报表生成脚本

### 1. 生成样例数据（含脏数据）

```bash
cd task1_excel_report
python make_sample_data.py            # 生成 ./sales_raw.xlsx
```

样例数据内置了空值行、重复行、数量为负/为 0 的脏数据，用于验证清洗逻辑。

### 2. 一键生成报表

```bash
python generate_report.py --input sales_raw.xlsx --output report.xlsx
```

运行成功后生成 `report.xlsx`，含 4 个工作表：
**明细清洗后 / 按销售员 / 按地区 / 总览**。

### 3. 运行测试

```bash
cd task1_excel_report
python -m pytest tests/ -v
```

测试覆盖：正常清洗与统计、空文件、缺列、全脏数据、原始文件不被修改等边界场景。

---

## 考题二：FastAPI 记账接口

### 1. 启动服务

```bash
cd task2_fastapi_ledger
uvicorn app.main:app --reload
```

服务默认运行在 http://127.0.0.1:8000，交互式文档见 http://127.0.0.1:8000/docs

### 2. 调用示例

```bash
# 新增一条收入
curl -X POST http://127.0.0.1:8000/records \
  -H "Content-Type: application/json" \
  -d '{"amount": 100.5, "type": "收入", "category": "工资", "date": "2026-10-01"}'

# 按类型+日期区间筛选，分页
curl "http://127.0.0.1:8000/records?type=支出&start_date=2026-10-01&end_date=2026-10-31&page=1&page_size=20"

# 区间汇总
curl "http://127.0.0.1:8000/summary?start_date=2026-10-01&end_date=2026-10-31"
```

### 3. 运行测试

```bash
cd task2_fastapi_ledger
python -m pytest tests/ -v
```

### 并发写入为什么不会产生数据错误（验收说明）

- 存储层选用 **SQLite + WAL 模式**：写操作在 `BEGIN IMMEDIATE` 事务内完成，
  SQLite 保证**同一时刻只有一个写者**，多线程并发写入在引擎层被串行化，
  不会出现交叉写坏或丢失更新；
- 每次请求使用独立短连接（用完即关），避免多线程共享连接的状态错乱；
- `id` 由 SQLite `AUTOINCREMENT` 在事务内生成，天然唯一，无并发重复主键风险；
- 极端高并发下写吞吐下降是可接受的（记账场景写频低），如需扩展可迁移
  PostgreSQL（`psycopg` + 连接池），接口层代码不变。

---

## 测试结果

两个考题的完整测试运行输出见 `docs/02_AI协作过程记录.md` 附录（含通过/失败统计）。

## 交付物清单对照

| 考核要求 | 对应文件 |
|---|---|
| 需求澄清清单 | `docs/01_需求澄清清单.md` |
| 可运行源代码工程（含 README） | 本仓库全部代码 + 本 README |
| 测试用例（正常 + ≥2 边界/异常） | `task1_excel_report/tests/`、`task2_fastapi_ledger/tests/` |
| AI 协作过程记录 | `docs/02_AI协作过程记录.md` |
| 文字复盘 | `docs/03_复盘.md` |
