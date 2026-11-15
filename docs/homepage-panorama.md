# 山海全景首页

按用户选定的第一版参考图实现，入口为 `travelmate/index.html`。没有新增依赖，保留现有认证、聊天、历史和攻略流程。

- 青绿山水全景、白色导航和宋体标题，配米白色悬浮选择栏。
- 五个主要下拉框：出发地、目的地、旅行天数、人均预算、旅行偏好；辅助下拉框选择同行人数，出发日期默认待定。
- 城市使用内置的国内目的地列表；新增城市时更新列表。原有快速规划仍可在对话中填写其他条件。
- 点击“生成我的行程”将所选条件整理为完整需求，沿用现有 `/chat/stream`。预算按所选区间上限乘以同行人数，明确传递人均口径、全员总预算及包含范围。
- 同城出发与到达时阻止提交。认证初始化和生成期间禁用生成按钮，避免重复提交。
- 四张推荐卡分别选择三亚 / 海边度假、莫干山 / 山野放空、成都 / 美食寻味、大理 / 古城漫游。只回填选择，不自动调用模型；保留天数、人数及预算。
- 随机目的地排除当前目的地和出发地；保留其他条件，用户确认后再生成。
- 首页隐藏文字输入框；进入对话后恢复输入、快速规划、语音和预设。返回首页保留已选条件，旅行手记继续使用真实历史。
- 桌面为横向选择栏和四列推荐；平板独立显示生成按钮行；手机为双列选择和双列推荐。

## 素材与生成提示词

使用内置 `image_gen` 生成，转换为 WebP 保存到 `travelmate/images/`，通过现有接口的明确白名单公开提供。原始 PNG 保留于 Codex 生成目录。全部素材要求单张照片、无文字、无界面、无水印：

| 保存路径 | 生成提示词 |
| --- | --- |
| `travelmate/images/home-panorama.webp` | 从第一版顶部重建干净全景：清晨喀斯特青绿群峰、雾气、蜿蜒碧绿江面、右侧暖日出和远处竹筏。保持参考构图与色调，移除全部界面；左侧略暗以承载白色标题。 |
| `travelmate/images/home-sea.webp` | 三亚热带海滩，左上椰树、象牙色弧形沙滩、清透浅海、远处绿色海岬，晴朗蓝天。高级旅行摄影。 |
| `travelmate/images/home-mountain.webp` | 莫干山林间度假，右前景现代木质玻璃小屋及温暖灯光，左侧层叠雾山，茂密竹叶。高级自然度假摄影。 |
| `travelmate/images/home-food.webp` | 成都四川铜制火锅，红汤、辣椒、花椒和蒸汽，周围新鲜食材，背景虚化的暖灯老街餐馆。高级美食摄影。 |
| `travelmate/images/home-town.webp` | 大理古城，灰瓦白族建筑、石板街、紫红三角梅，远处蓝色洱海及苍山，晴朗温暖午后。高级旅行摄影。 |

推荐图为横向 3:2，主体位于中上部，下方适度暗色，供网页叠加白色文案。

## 验证

- `node --test tests/homepage.test.mjs tests/quick-fill.test.mjs tests/markdown.test.mjs tests/auth.test.mjs tests/voice.test.mjs tests/back-to-top.test.mjs`：52 项通过。
- `.venv/Scripts/python.exe -m pytest tests/test_auth.py tests/test_sessions.py tests/test_interaction.py tests/test_streaming.py tests/test_preparation.py tests/test_preparation_items.py tests/test_daily_ui.py tests/test_guide.py -q`：49 项通过。
- Chrome 检查 1536×1024、1280×900、820×1180、390×844、320×780：图片、溢出、回填、随机排除、同城校验、历史弹窗与 Esc、预算转换、CSRF、生成后聊天、快速规划及返回首页通过。
- 截图在 `output/homepage-panorama-v1/`。验证使用隔离本地服务、虚拟账号和模拟响应，没有读取真实历史或调用付费模型。
- `git diff --check` 通过。未部署，未验证 Safari 或真实手机软键盘。
