# TravelMate 免费 12306 MCP 接入教程（Windows）

## 先说明费用和来源

本项目接入的是第三方开源 [Joooook/12306-mcp](https://github.com/Joooook/12306-mcp)，不是铁路官方 MCP。项目采用 [MIT 许可](https://github.com/Joooook/12306-mcp/blob/main/LICENSE)，代码可免费使用，本地部署不需要购买 API Key 或 MCP 订阅。不要将其与付费平台托管的同名服务混淆。

MCP 软件免费不代表整个智能体零成本：模型 API、已有知识库和云主机仍按各自服务计费。车次查询按钮直接访问本地 MCP，不调用模型。网页和 MCP 的网络请求依赖 12306 网站的可用性；本项目只查询，不登录、不购票、不处理支付。请遵守数据提供方的使用规则，不高频轮询或绕过访问限制。

本次实测上游0.3.10的SSE传输可以完成握手；其HTTP传输与当前客户端组合出现400，因此这里统一使用SSE端点。

接入使用 Python 官方 MCP SDK（`mcp<2`）和 MCP SSE，不需要把 MCP 安装到 Codex。架构：浏览器 → TravelMate `/transport/trains` → 本地 MCP → 12306。聊天里的铁路查询也使用同一工具。

## 1. 准备环境

打开 PowerShell，进入项目：

```powershell
Set-Location E:\travelmate-agent\travelmate-agent
node --version
uv --version
```

推荐 Node.js 22 LTS 或更新的受支持 LTS。没有 Node 时，从 [Node.js 官网](https://nodejs.org/)安装 LTS，安装后重新打开 PowerShell。没有 uv 时按 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/)安装。

## 2. 安装 Python 查询依赖

```powershell
uv sync --extra dev --extra aliyun --extra rail
```

`rail` 安装 MCP 客户端；`aliyun` 保留本项目已有的阿里云知识库依赖，不会自动购买服务。仅使用本地知识库也可执行 `uv sync --extra dev --extra rail`。今后用 uv 启动时也带上 `--extra rail`，防止 uv 移除可选依赖。

## 3. 启动免费的本地 MCP

另开一个 PowerShell 窗口，运行：

```powershell
Set-Location E:\travelmate-agent\travelmate-agent
npx.cmd --cache ./data/npm-cache --registry https://registry.npmjs.org --yes 12306-mcp@0.3.10 --host 127.0.0.1 --port 8081
```

首次会下载 npm 包，时间可能较长。命令固定顶层版本为 0.3.10；上游的依赖仍由 npm 解析。缓存放在项目忽略的 `data` 目录，避免机器默认 npm 缓存目录无权限。`npx.cmd` 避免 PowerShell 对 `.ps1` 的执行策略限制。后续启动可复用缓存。

保持该窗口运行，看到服务监听日志后再进行下一步。仅绑定 `127.0.0.1`，浏览器不直接连接 MCP；不要为了本机使用将它暴露到公网。停止时在该窗口按 Ctrl+C。

## 4. 配置 TravelMate

用编辑器打开项目根目录 `.env`。如果没有，从 `.env.example` 复制一份，再填写已有模型配置。保留原来的密钥，只增加或修改这一行（不要重复添加）：

```dotenv
RAIL_MCP_URL=http://127.0.0.1:8081/sse
```

这里没有铁路 API Key。将这行值留空可以关闭车次查询，不影响攻略生成。修改 `.env` 后重启 TravelMate；已有进程不会自动重新加载此项。

## 5. 启动网页服务

在另一个 PowerShell 窗口运行：

```powershell
Set-Location E:\travelmate-agent\travelmate-agent
uv run --extra rail --extra aliyun uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000`。如原来的 8000 端口已有服务，请先停止并重新启动原服务，或换用 8002 等空闲端口。首次启用时至少需要 MCP 和 TravelMate 两个进程运行。

## 6. 在页面查询车次

1. 展开底部“快速规划”。
2. 选择“高铁”“动车”或“火车”。高铁筛选 G/C，动车筛选 D，火车查询全部列车类型。
3. 填写出发地、目的地、出发日期，例如“上海虹桥 → 北京南”，日期选择近期已开售日期。
4. 点击“查询铁路车次”。此操作不要求先填预算和人数，也不会消耗模型调用。
5. 面板最多显示 8 个车次，包含车站、出发/到达日期时间、历时、席别票价与余票。跨日抵达以返回的抵达日期为准。
6. 填写人数、预算和天数后点击“生成旅行需求”，检查输入框中的草稿，再发送给智能体。

也可以直接聊天：“两个人，明天从上海虹桥到北京南，交通选高铁，预算3000元，玩3天，查车次并规划。”模型会使用相同的铁路工具。必须以工具结果为依据，查询失败时明确显示未核实。

输入城市名时，上游按城市代表站查询，并非保证覆盖同城所有车站。希望指定站点时直接填写“上海虹桥”“北京南”“厦门北”等站名；请不要附带省名，比如用“厦门”，不用“福建厦门”。

## 7. 暂未确定出发地或日期

这两项可留空，目的地、天数、人数和预算仍要填。点击“生成旅行需求”后，智能体按第1天、第2天规划，不会猜测日期或出发城市，也不默认调用高德。未定日期不会伪造铁路车次或实时票价。

选择飞机、自驾、其他或不限时，不调用 12306。自驾路线可按需查询高德；机票暂未接入专门数据源。不要将铁路票价当成航空票价。

## 8. 不经过模型的接口检查

保持两个服务运行，在 PowerShell 执行：

```powershell
$railQuery = @{
  origin = '上海虹桥'
  destination = '北京南'
  departure_date = (Get-Date).AddDays(1).ToString('yyyy-MM-dd')
  transport = '高铁'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/transport/trains' -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($railQuery)) | ConvertTo-Json -Depth 10
```

这段命令使用本机日期，跨时区部署时请确认出发日期按北京时间填写。`results` 有内容表示取得车次；空列表只表示没有匹配结果，不能据此断言售罄。`error` 表示服务未启用、输入有误或查询失败。上游故障不会回传服务器内部异常详情。

## 9. 常见问题

| 表现 | 处理 |
| --- | --- |
| 提示尚未启用 | 检查 `.env` 的 `RAIL_MCP_URL`，保存后重启网页服务 |
| 缺少依赖 | 执行带 `--extra rail` 的安装和启动命令 |
| 连接失败或超时 | 检查 MCP 窗口是否运行、8081 是否占用、地址是否含 `/sse`；总查询超时为30秒 |
| 服务启动失败，提示获取12306页面失败 | 确认本机能访问12306；上游页面可能变更或暂时拒绝访问，不要绕过限制。仍可正常生成攻略 |
| 没有车次 | 检查日期是否已开售、是否有直达列车、车站是否正确；尝试具体车站。实际预售范围以12306为准 |
| 城市/站点未找到 | 去掉省名或选择具体站名；不要把地铁站、机场当作火车站 |
| 没有票价或席别 | 显示上游实际返回的信息，缺失不表示免费；以12306下单页面为准 |
| npx 没有权限 | 使用教程中指定的本地 `--cache ./data/npm-cache`，无需修改全局 npm 设置 |
| 页面仍然是旧版本 | 重启后端并刷新浏览器，核对启动目录 |

## 10. 回归检查

```powershell
uv run --extra dev --extra rail --extra aliyun pytest -q
node --test tests/markdown.test.mjs tests/quick-fill.test.mjs
```

自动化测试覆盖输入校验、铁路类型筛选、MCP 握手与调用参数、错误脱敏、缺少出发地/日期的行程及PDF、页面请求与失败提示。测试中的车次为模拟数据；真实上游查询的可用性需要在部署网络下单独验证。

## 本次联调记录

已实际启动 npm 0.3.10，并通过SSE完成MCP握手、站点解析和真实余票查询。2026年11月3日测试“11月4日上海虹桥 → 北京南、高铁”，取得车次、发到时间、席别价格和余票数据。曾在沙箱内遇到 `get cookie failed`，定位为出站网络权限不足；允许联网后查询成功。以上只记录联调结果，不保证后续价格或库存不变。

## 参考

- [开源项目与启动方式](https://github.com/Joooook/12306-mcp)
- [MIT 许可](https://github.com/Joooook/12306-mcp/blob/main/LICENSE)
- [上游工具定义](https://github.com/Joooook/12306-mcp/blob/main/src/index.ts)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
