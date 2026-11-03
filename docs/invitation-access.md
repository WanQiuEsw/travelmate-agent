# 邀请体验与低成本部署

网页默认开启邀请认证。账号、邀请码、登录态、会话归属和每日用量都写入 `DATABASE_PATH` 指向的现有 SQLite，不需要 MySQL、Redis、ORM、短信或邮件服务，没有新增 Python 依赖。启动时仅增加 `auth_` 前缀的表，不修改已有 checkpoint 数据。

## 本地启动与发放邀请

在项目目录编辑 `.env`，保留现有模型配置，并增加：

```dotenv
DATABASE_PATH=data/checkpoints.sqlite
AUTH_DAILY_LIMIT=20
AUTH_GLOBAL_DAILY_LIMIT=100
AUTH_SESSION_DAYS=7
AUTH_COOKIE_SECURE=false
```

`false` 仅适用于本地 HTTP 开发；服务器 HTTPS 必须使用 `true`，默认也是 `true`。这不是关闭认证的开关。修改配置后重启服务。

若 HTTP 页面配合 `AUTH_COOKIE_SECURE=true`，服务端会在消耗邀请码前明确拒绝，提示修正配置。页面在登录或注册后还会确认 Cookie 登录态已保存，避免注册成功后反复返回登录页。出现“无法连接登录服务”表示请求未能正常完成，请检查服务进程；若请求中断前已完成注册，可直接切换登录，无需再次使用邀请码。

```powershell
uv run python -m travelmate.accounts invite --count 5 --days 7
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000 --workers 1
```

第一条命令生成 5 个邀请码，每个有效 7 天、只能注册一个账号。只有创建时显示原文，数据库只保存摘要。通过你已有的私下渠道将不同邀请码交给不同用户。

打开 `http://127.0.0.1:8000/login`，选择“有邀请码？注册账号”，填写用户名、密码、昵称和邀请码。用户名为 3–32 位字母、数字或下划线，忽略大小写；密码为 12–128 个字符；昵称可选。注册后自动登录，后续使用用户名和密码登录。

首页检查登录态，未登录时进入登录页。浏览器只持有 HttpOnly Cookie，不向 localStorage 写入密码或登录令牌。聊天页面显示昵称、剩余额度，并提供退出登录。

## 额度与归属规则

- 默认每人每天 20 次生成，全站共 100 次，均按北京时间零点重新计算。重启、退出重登、删除或新建会话不会重置额度。
- `/chat` 与 `/chat/stream` 共用额度，每次用户提交并被服务端接受的聊天请求扣一次，包括追问与修改需求。这不是“完整行程一次”，也不是模型实际调用一次。
- 参数无效、越权、额度不足或服务繁忙时不扣。请求已被接受后，即使模型失败或浏览器断开，仍计一次，因为后台可能已经发生付费调用。不会自动重试整条聊天请求。
- 全站上限限制请求次数，不是人民币费用上限；一次规划可能调用多个模型节点和工具，仍需在服务商处配置合适的预算和告警。
- 查看历史、修改标题、删除、置顶和导出已有结果不扣生成额度。普通接口每账号最多 120 次/分钟，PDF 最多 20 次/分钟；独立铁路查询最多 10 次/分钟、100 次/固定 24 小时窗口。
- 登录按连接 IP 限制 20 次/15 分钟，按用户名限制 10 次/15 分钟；注册按 IP 限制 5 次/小时，成功与失败都计数。固定窗口边界可能出现短时突发。
- 历史、行程、预览、PDF 和所有单条/批量修改接口都校验归属。批量请求含有他人会话时，整批拒绝。
- 遗留本地会话继续保留，不会自动归入任何新账号，猜到旧 ID 也不能认领。删除后的会话 ID 仍保留归属，防止被其他账号占用。
- 目前同时只执行一个生成任务；忙时返回 409，用户稍后重试。适合小范围邀请体验，不应通过增加 worker 扩大并发。

## 管理账号

管理操作通过服务器终端执行，不提供公开管理员接口。务必在相同项目目录、加载相同 `.env` 后执行，或使用 `--database` 显式指定线上文件。

```powershell
# 查看账号和今日用量
uv run python -m travelmate.accounts users

# 修改个人每日额度；0 表示暂停生成，仍可查看历史
uv run python -m travelmate.accounts user alice --daily-limit 10

# 禁用账号并注销其所有登录；恢复账号
uv run python -m travelmate.accounts user alice --disable
uv run python -m travelmate.accounts user alice --enable

# 管理员重置密码：交互输入不回显，同时注销原有登录
uv run python -m travelmate.accounts reset-password alice

# 撤销尚未使用的邀请码
uv run python -m travelmate.accounts revoke-invite <邀请码>
```

个人额度覆盖 `AUTH_DAILY_LIMIT`，但仍受全站上限约束。禁用账号不会取消已经开始的生成；之后的请求会被拒绝。首版没有自助找回密码、付费套餐、邮件验证和管理后台。

## 服务器部署

1. `DATABASE_PATH` 使用持久化目录，升级前备份已有数据库。运行时可用 SQLite backup API，停服后也可复制完整数据库。备份包含明文聊天和密码哈希，不能放到静态文件目录。
2. `.env` 设置 `AUTH_COOKIE_SECURE=true`，使用域名与 HTTPS 反向代理。应用只监听 `127.0.0.1:8000`，公网不开放 8000。使用 `--workers 1`，不使用 `--reload`。
3. 在已有 Nginx HTTPS `server` 内配置下面的 location；证书由现有证书配置负责：

```nginx
location / {
    client_max_body_size 64k;
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
}
```

启动命令：

```bash
uv run uvicorn travelmate.api:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

仅信任实际代理地址，不要设置 `--forwarded-allow-ips '*'`，以免被伪造 IP 绕过限流。应用不直接读取客户端的 `X-Forwarded-For`。代理在其他机器或容器时，按实际网络修改监听、防火墙及可信代理地址。

`/health` 公开，仅返回进程状态。`/docs`、`/redoc`、`/openapi.json` 默认关闭。API 调用方先通过 `/auth/register` 或 `/auth/login` 建立 Cookie 会话；写操作需要 `X-TravelMate-Request: 1`。若带 `Origin`，必须与本站地址一致；不要添加宽松跨域配置。登录及普通 API 响应禁止缓存。

Python CLI `uv run travelmate --session ...` 仍是可信服务器维护工具，不经过网页认证与额度。不要向普通用户提供服务器终端或数据库文件。

## 验证

```powershell
uv run pytest -q
node --test tests/markdown.test.mjs tests/quick-fill.test.mjs tests/auth.test.mjs
```

认证测试使用临时 SQLite 和离线模型，不读写正式账号或额度，也不调用付费模型。
