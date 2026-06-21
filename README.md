# 演出票务与场次座位管理平台（纯后端）

演出剧目、场次与购票订单管理的纯后端 API 服务，作为 Feature 迭代题的基座工程。

## 技术栈

- Python + Django + Django REST Framework
- MySQL 8（字符集 utf8mb4），通过 PyMySQL 连接
- JWT 鉴权（djangorestframework-simplejwt）
- Gunicorn 运行

## 启动（Docker）

```bash
docker compose up --build
```

MySQL 就绪后，应用容器自动执行数据库迁移、灌入种子数据，服务监听 `http://127.0.0.1:7652`。

## 运行测试

```bash
DJANGO_TEST=1 python manage.py test
```

测试使用 SQLite 内存数据库，不依赖 MySQL 服务。

## 内置账号

唯一管理员（本平台只有 admin 一个角色）：

- 用户名：`admin`
- 密码：`admin123`

## 已实现的基础功能

- 登录签发 JWT、获取当前用户（`/api/auth/login`、`/api/auth/me`）
- 演出剧目增删改查（`/api/shows`）
- 场次增删改查（`/api/performances`）
- 购票下单（带余票校验、自动算金额并扣减库存）与订单查询（`/api/orders`）
- 仪表盘统计（`/api/dashboard/stats`）
- 健康检查（`/api/health`）

除 `login` 与 `health` 外，接口均需 `Authorization: Bearer <token>`。

## 座位图选座购票功能

### 核心模型

- **Hall** — 厅（如"一号厅"）
- **SeatTemplate** — 厅座位模板，含 `zone`（区）、`row`（排）、`number`（座号）、`grade`（VIP/A/B）
- **PerformanceSeatPrice** — 场次按座位等级定价
- **PerformanceSeat** — 场次可售座位，状态三态：`available` / `locked` / `sold`
- **TicketOrder** — 订单，三态：`pending`（待支付）/ `paid`（已支付）/ `cancelled`（已取消）
- **OrderSeat** — 订单与座位关联

### 接口速览

| 方法 | 路径                                    | 说明                                               |
| ---- | --------------------------------------- | -------------------------------------------------- |
| POST | `/api/halls/{id}/init-seats`            | 厅座位初始化（批量生成 SeatTemplate）              |
| POST | `/api/performances/{id}/generate-seats` | 场次座位生成（从厅模板 + 按等级定价）              |
| GET  | `/api/performances/{id}/seat-map`       | 查场次座位图（按区→排→座层级返回，含状态和价格）   |
| POST | `/api/performances/{id}/lock-seats`     | 选座锁座（生成 pending 订单，座位锁定 10 分钟）    |
| POST | `/api/orders/{id}/pay`                  | 支付订单（只有待支付且归属自己的订单可支付）       |
| POST | `/api/orders/{id}/cancel`               | 取消订单（释放锁定座位，只能取消自己的待支付订单） |
| POST | `/api/seats/release-expired`            | 释放所有过期锁座                                   |
| GET  | `/api/performances/{id}/seat-stats`     | 场次售座统计（总/已售/锁定/可售 + 各等级分项）     |

### 接口详情

---

**1. 厅座位初始化**

```
POST /api/halls/{id}/init-seats
```

请求体：

```json
{
  "zones": [
    {
      "name": "VIP区",
      "grade": "VIP",
      "rows": [
        { "row": "1", "seats": 12 },
        { "row": "2", "seats": 14 }
      ]
    },
    {
      "name": "A区",
      "grade": "A",
      "rows": [{ "row": "3", "seats": 16 }]
    }
  ]
}
```

响应：

```json
{ "hall_id": 1, "created": 42, "total_templates": 42 }
```

---

**2. 场次座位生成**

```
POST /api/performances/{id}/generate-seats
```

请求体：

```json
{ "prices": { "VIP": 880, "A": 580, "B": 380 } }
```

响应：

```json
{ "performance_id": 1, "generated": 160 }
```

---

**3. 查场次座位图**

```
GET /api/performances/{id}/seat-map
```

响应示例（精简）：

```json
{
  "performance_id": 1,
  "show_title": "星河巡回演唱会",
  "hall_name": "星河大剧院",
  "start_at": "2026-06-24T20:00:00",
  "prices": [
    { "id": 1, "performance": 1, "grade": "VIP", "price": "880.00" },
    { "id": 2, "performance": 1, "grade": "A", "price": "580.00" },
    { "id": 3, "performance": 1, "grade": "B", "price": "380.00" }
  ],
  "zones": [
    {
      "zone": "VIP区",
      "grade": "VIP",
      "rows": [
        {
          "row": "1",
          "seats": [
            {
              "id": 1,
              "zone": "VIP区",
              "row": "1",
              "number": "1",
              "grade": "VIP",
              "price": "880.00",
              "status": "sold"
            },
            {
              "id": 2,
              "zone": "VIP区",
              "row": "1",
              "number": "2",
              "grade": "VIP",
              "price": "880.00",
              "status": "locked"
            },
            {
              "id": 3,
              "zone": "VIP区",
              "row": "1",
              "number": "3",
              "grade": "VIP",
              "price": "880.00",
              "status": "available"
            }
          ]
        }
      ]
    }
  ]
}
```

座位状态：`available`（可售）/ `locked`（锁定）/ `sold`（已售）。

---

**4. 选座锁座**

```
POST /api/performances/{id}/lock-seats
```

请求体：

```json
{
  "seat_ids": [101, 102, 103],
  "customer_name": "张三",
  "phone": "13800001234"
}
```

座位只能是 `available` 状态，否则返回 409。锁座有效期 10 分钟。

响应（201 Created）：

```json
{
  "id": 1,
  "performance": 1,
  "show_title": "星河巡回演唱会",
  "user_id": 1,
  "customer_name": "张三",
  "phone": "13800001234",
  "amount": "1740.00",
  "status": "pending",
  "locked_until": "2026-06-21T13:10:00",
  "seats": [
    {
      "id": 1,
      "zone": "A区",
      "row": "3",
      "number": "1",
      "grade": "A",
      "price": "580.00"
    },
    {
      "id": 2,
      "zone": "A区",
      "row": "3",
      "number": "2",
      "grade": "A",
      "price": "580.00"
    },
    {
      "id": 3,
      "zone": "A区",
      "row": "3",
      "number": "3",
      "grade": "A",
      "price": "580.00"
    }
  ],
  "created_at": "2026-06-21T13:00:00"
}
```

---

**5. 支付订单**

```
POST /api/orders/{id}/pay
```

- 只能支付**自己的** `pending` 订单
- 锁座过期则支付失败（410 Gone），座位自动释放
- 订单状态变为 `paid`，座位变为 `sold`

---

**6. 取消订单**

```
POST /api/orders/{id}/cancel
```

- 只能取消**自己的** `pending` 订单
- 座位释放回 `available`，订单状态变为 `cancelled`

---

**7. 释放过期锁座**

```
POST /api/seats/release-expired
```

扫描所有 `pending` 且 `locked_until < 当前时间` 的订单，释放座位。

响应：

```json
{ "released_orders": 2 }
```

---

**8. 场次售座统计**

```
GET /api/performances/{id}/seat-stats
```

响应：

```json
{
  "performance_id": 1,
  "show_title": "星河巡回演唱会",
  "hall_name": "星河大剧院",
  "total": 160,
  "sold": 5,
  "locked": 3,
  "available": 152,
  "grade_stats": [
    { "grade": "VIP", "total": 26, "sold": 5, "locked": 0, "available": 21 },
    { "grade": "A", "total": 50, "sold": 0, "locked": 3, "available": 47 },
    { "grade": "B", "total": 84, "sold": 0, "locked": 0, "available": 84 }
  ]
}
```

### 并发安全

- 锁座使用 `select_for_update()` 行级排他锁 + 数据库事务，确保同一座位不会被两个订单同时锁住
- 支付/取消同样使用行级锁保护
- 锁座前自动清理该场次已过期的锁座

## 编码说明

数据库使用 utf8mb4；DRF 开启 UNICODE_JSON，中文以 UTF-8 原样返回、不转义。
