# 山水长卷首页

按用户选择的第三版参考图实现，入口为 `travelmate/index.html`。

- 顶部品牌、首页、我的行程和账户菜单；历史管理改为原生 dialog 抽屉，保留置顶、重命名、多选删除，支持 Escape 关闭及焦点恢复。
- 杭州湖景横幅、宋体标题、悬浮规划框；快速规划继续打开现有分步表单，语音与预设入口保留。
- 山野、古城和海边主题，以及杭州、成都、厦门目的地，只填写草稿，不自动发送；生成时不覆盖草稿。
- 旅行手记显示历史列表中的第一条行程（沿用置顶优先的顺序）。从该对话最后一条成功且有版本号的助手消息获取攻略入口，不伪造路线或天数。无历史、加载失败、未生成攻略均有对应状态。
- 聊天后隐藏横幅和首页内容，保留独立对话滚动区与底部输入框。刷新仍沿用原有的会话恢复逻辑；点击首页可开始新对话，已有对话仍在历史中；在空白首页点击首页不会清空草稿。

图片直接复用 `travelmate/images/cities/` 与现有品牌素材，无新增图片、依赖、模型调用或后端接口。未改动登录页和攻略详情页。

## 验证

- `node --test tests/markdown.test.mjs tests/quick-fill.test.mjs tests/auth.test.mjs tests/voice.test.mjs`：46 项通过。
- `.venv/Scripts/python.exe -m pytest tests/test_auth.py tests/test_sessions.py tests/test_interaction.py tests/test_streaming.py -q`：34 项通过。
- 本机 Chrome 检查 1536×1024、820×1180、390×844、320×780：图片正常，无横向溢出；检查主题与目的地填入、首页草稿保留、快速规划、历史弹窗焦点、继续行程、返回首页、消息发送和空历史状态，无未捕获异常。
- 截图在 `output/homepage-refresh/`，其中的行程为隔离预览数据，没有使用线上账号、私人记录或付费模型。
- `git diff --check` 通过。未部署，未验证 Safari 或真实手机软键盘。
