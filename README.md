# Vouchpin（券钉簿）

骨架：券事件入湖 → 核销事实钉扎 → 过期/退回窗（后挖）→ 批次互证。

## 钉扎范围粒度（全局互斥）

本系统只贯彻**一种**粒度：**按活动分批钉**。

- 每次钉扎指定 `campaign_code`，只吃掉该活动在该业务日的 `open` 核销事实，
  落一条活动级 `sealed` 批（`redeem_batches.scope='campaign'`）。
- **写闸**：已钉活动禁止再写入该活动核销；未钉活动仍可核销、仍可钉扎。
  写入时校验与钉扎同粒度，不存在「整日一把钉」导致的漏拦。
- **不许补钉**：已钉活动再次钉扎 → 409；同一活动并发钉扎由 `BEGIN IMMEDIATE`
  + 唯一索引互斥，只会有一个成功，其余 409。
- **禁止混用整日钉扎**：`scope='day'` 的请求一律 409；历史上遗留的整日批会被识别，
  该日视为已整日封存，不得再按活动补钉。
- **合计等式**（总览 / 预览 / 批次一致）：
  `日核销额 = open 合计 + 已钉活动批合计`；每批金额 = 批内事实金额之和。

接口：
- `GET /api/redeem/preview?business_day=&campaign_code=` — 活动汇总、范围明细、合计等式
- `POST /api/redeem/seal {"campaign_code": "NEW10"}` — 按活动钉扎
- `GET /api/dashboard` — 含 `ledger`（同日等式与 `balanced`）

核对：`cd backend && python -m unittest discover -s tests -v`（需先装 requirements）

本地：
- API: `cd backend && python -m uvicorn app.main:app --port 10800`
- Web: `cd frontend && npm install && npm run dev`（5800）
