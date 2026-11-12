# 本地演示：小红书优先、百炼补充

小红书用于发现景点、美食、游览路线和避坑线索。资料不足时补查现有知识库（支持百炼）；价格、开放时间、预约、天气和车次继续走原有独立核实流程。

## 配置

```powershell
uv sync --all-extras
```

在项目根目录 `.env` 中配置：

```dotenv
KNOWLEDGE_PROVIDER=aliyun
# 保留已有的 ALIBABA_CLOUD_*、ALIYUN_WORKSPACE_ID、ALIYUN_INDEX_ID 配置
XHS_ENABLED=true
XHS_COOKIE="填入网页端登录后的 Cookie"
```

获取 Cookie：自己在浏览器中登录小红书网页，打开开发者工具的 Network 面板，搜索一次旅游攻略，选择发往 `edith.xiaohongshu.com` 的请求，复制 Request Headers 中的 Cookie 值。必须包含 `a1` 和 `web_session`，建议复制完整值。也支持浏览器导出的 Cookie JSON 数组。

Cookie 只放在本地 `.env`，不要发到聊天、截图或提交到 Git。无需提供账号密码。遇到登录失效或访问限制，先在浏览器正常登录、确认网页可用，再更新 Cookie；程序不会自动解验证码或反复重试。

## 先单独检查数据入口

```powershell
uv run --all-extras python -m travelmate.xhs 杭州
```

此命令只调用小红书，不调用大模型或百炼。成功时打印笔记正文、公开链接、发布时间和新鲜度；空结果也会明确返回。

常见错误：`not_configured` 未配置或已关闭；`invalid_cookie` 缺少必要 Cookie；`missing_dependency` 未安装 xhs extra；`login_or_risk_control` 登录态失效或平台限制；`search_unavailable` 网络或响应异常；`signing_failed` 签名失败。不要将这些错误解释成“该城市没有攻略”。

## 启动完整演示

```powershell
uv run --all-extras uvicorn travelmate.api:app --host 127.0.0.1 --port 8000
```

本地 HTTP 沿用 `AUTH_COOKIE_SECURE=false` 和现有邀请码登录流程。改 `.env` 后重启服务。

示例需求：从上海出发，两个人，2026年12月1日去杭州一天，总预算1000元，包含全部费用，喜欢西湖和当地美食，少走路。先确认日期和预算口径，再生成攻略。

进度会显示小红书检索及知识库补充。攻略“参考来源”保留小红书笔记链接和发布时间，HTML、Markdown 与 PDF 沿用同一份来源数据。没有 Cookie 时仍可用百炼生成攻略，但这不代表小红书接入验证成功。

## 当前范围

- 一个最新排序的搜索页，最多取前8个搜索条目中的4篇笔记正文，总网络时间预算约18秒，不自动重试。
- 优先采用近30天；近30天有效结果少于2篇时保留近90天内容。发布时间未知会明确标记，超过90天的笔记不使用。
- 按城市和现有主题覆盖规则过滤，资料不全时补知识库；知识库仍缺少的主题继续联网检索。
- 发布时间、更新时间、查询时间分开记录；不能保证覆盖全站最新笔记。来源链接可能要求登录，小红书也可能限制直接打开。
- 不采集图片、评论、视频或图片内文字；本版不把笔记自动写入百炼，不增加后台采集任务。行前刷新继续核实价格、开放和交通，不自动重采社区笔记。
- 采用与 TripStar 类似的网页接口方式，自有接入代码使用 `xhshow` 签名依赖，无需 Node.js；没有复制 TripStar 的签名资源。网页接口或签名变化可能导致失效，低频个人演示也无法保证持续可用。

参考：[TripStar](https://github.com/1sdv/TripStar)、[xhshow](https://github.com/Cloxl/xhshow)。
