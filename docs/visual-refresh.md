# TravelMate 视觉优化

## 范围与目的

| 调整 | 目的 |
| --- | --- |
| 统一暖白、海湾青绿、深墨绿和少量暖橙 | 将办公感的灰蓝界面转为轻松、清晰的旅行品牌；主按钮与背景有明显区别 |
| 使用系统无衬线字体、16px 正文、分级标题与统一间距 | 保持现代感和长行程的阅读舒适度，无需外部字体请求 |
| 首页左右分栏标题与山海影像 | 建立旅行氛围，同时让主要操作保持清楚 |
| 输入框紧接欢迎区，区分快速规划、示例和发送按钮 | 缩短从产生出行想法到输入需求的路径；保留原有控件 ID 和处理逻辑 |
| 三张旅行灵感卡 | 为未确定目的地的用户提供起点；复用 fillTripDraft，只填草稿，忙碌时不覆盖输入，不自动提交 |
| 山海行李箱标志、海鸥旅伴头像 | 分别承担小尺寸品牌识别和角色陪伴，不将复杂插画当作交互图标 |
| 历史记录与账户分区 | 历史记录更突出；账户、额度、退出收拢到底部；保留置顶、多选、删除等原功能 |
| 聊天后收起首图及灵感卡 | 避免长回复被营销内容挤占；继续保留原有独立对话滚动区和底部输入区 |
| 登录页延续山海画面、颜色与控件细节 | 让登录入口与主产品拥有统一品牌，保留注册切换、校验和错误展示 |
| 手机端单列、品牌始终可见、横向灵感卡 | 保持窄屏可读与触控尺寸，保留可折叠历史区域 |
| 焦点轮廓、减少动态、图片尺寸与替代文本 | 保留键盘操作、减少布局跳动，不靠颜色单独传递交互状态 |

## 资产与来源

所有新增位图由本次会话的内置 image_gen 工具生成，无外部素材下载、无第三方商标、无外部图标库或字体。

- `travelmate/images/coast.webp`：山海首图，1280px，用于首页与登录页，也复用于海岸灵感卡。
- `travelmate/images/mountains.webp`、`town.webp`：720px 灵感配图。
- `travelmate/images/companion.webp`：256px，来自上一轮海鸥旅行家参考图。
- `travelmate/images/icon.webp`：192px，来自上一轮山海行李箱参考图，用于品牌标志和 favicon。
- 位图仅缩放及转换 WebP 以适合网站加载；五张合计约 565 KiB。图片在本地提供，卡片图片延迟加载。
- 页面明确标注 AI 旅行意境图，图片不被描述为特定真实目的地的实拍。
- 原有操作图标继续使用项目已有的 SVG 路径。新增箭头使用文本符号。

## 发布注意

共享配色位于 `travelmate/theme.css`。图片及 CSS 已加入 Python 包数据，API 仅公开指定的视觉文件；业务鉴权规则保持。

本次仅优化视觉及新增灵感填写入口，不改变模型、行程、铁路查询、登录策略或导出逻辑。

## 验证

- 33 项前端测试通过：聊天渲染与流式输出、历史管理、输入法、快速规划、登录注册，以及新增灵感卡只填草稿、忙碌时不覆盖输入。
- 32 项相关后端测试通过：账户、静态素材访问范围、会话、流式输出和交互补充。
- 实际浏览器检查了 1280×720、1440×1000、820×1180、390×844 布局，无横向溢出，图片正常加载。
- 用隔离 SQLite 和离线测试模型验证登录、聊天回复、刷新恢复、首页收起装饰、历史菜单、多选、手机折叠历史与注册表单；未调用付费模型或线上业务数据。
- wheel 构建成功并检查包含共享 CSS 和全部五张图片；`git diff --check` 通过。
- 实际截图位于 `output/visual-refresh/`：桌面首页、桌面登录页、手机首页、手机聊天页、手机登录页。
- 本次没有发布到线上，也没有测试真实手机软键盘和 Safari；新增视觉素材与现有系统字体不需要外部 CDN。

## 旅行配图生成提示词

### 1

Use case: photorealistic-natural. Asset: locally hosted travel inspiration photography for TravelMate AI travel planner homepage. Wide landscape 1536x1024 composition, premium contemporary travel magazine photo, warm natural daylight, clear atmospheric depth, authentic beautiful colors, turquoise/forest-teal greens and warm stone, no oversaturation, no grain, no text, no borders, no watermarks, no logos. Imaginary scenic destination; no claim to a named real place. Sunlit winding walking trail along a lush mountainous Mediterranean-like coast, turquoise clear sea, green rugged headlands receding in distance, warm light clouds and sky, small two hikers with backpacks very far along trail to convey scale. Beautiful inviting adventurous mood, right side mountains and trail, left side ocean. No large foreground people or buildings.

### 2

Use case: photorealistic-natural. Asset: locally hosted travel inspiration photography for TravelMate AI travel planner homepage. Wide landscape 1536x1024 composition, premium contemporary travel magazine photo, warm natural daylight, clear atmospheric depth, authentic beautiful colors, turquoise/forest-teal greens and warm stone, no oversaturation, no grain, no text, no borders, no watermarks, no logos. Imaginary scenic destination; no claim to a named real place. Fresh green layered mountain valley and lush meadow, curving footpath leads toward distant mountain peaks, early morning mist between ridges, sunshine through soft clouds, tiny lone hiker far away, inviting restorative outdoors. Balanced panoramic landscape, not snowy, not dramatic fantasy.

### 3

Use case: photorealistic-natural. Asset: locally hosted travel inspiration photography for TravelMate AI travel planner homepage. Wide landscape 1536x1024 composition, premium contemporary travel magazine photo, warm natural daylight, clear atmospheric depth, authentic beautiful colors, turquoise/forest-teal greens and warm stone, no oversaturation, no grain, no text, no borders, no watermarks, no logos. Imaginary scenic destination; no claim to a named real place. Quiet historic Chinese canal town, stone pedestrian bridge over green water, whitewashed houses with dark tiled roofs, a small warm lantern, willow leaves, soft morning sunlight, a few tiny distant pedestrians, refined authentic travel photography, no readable shop signs or lettering.
