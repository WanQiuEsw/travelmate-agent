# 避坑指南素材与页面

入口：图文攻略中的「避坑指南」，锚点 `#panel-pitfalls`。

`travelmate/pitfalls_ui.py` 使用现有攻略数据，展示四条通用提醒，并完整保留已保存的专属提醒与安全来源链接。预订前展示完整准备清单；其他阶段筛选相关通用提醒。专属提醒始终展示，避免漏读。移动端改为单列，支持键盘选择阶段；导出 HTML 内嵌图片，打印展示全部提醒。PDF 和 Markdown 继续使用原攻略内容。

## 可复用素材

- `travelmate/images/hotel-room.webp`：576 × 384，AI 生成的住宿示意图。桌面使用 194 × 102 CSS 像素，手机使用 48 × 48 并裁切；其他旅游攻略可通过 `/assets/visual/hotel-room.webp` 复用。
- 风景复用现有城市/主题 WebP 图片，随攻略目的地选择。
- 常用图标复用现有 `budget_ui.icon`，新增日历、定位、飞机、场景与建议图标保存在 `pitfalls_ui.icon`。行李箱插画为 SVG，任意屏幕分辨率均可清晰显示。

住宿图使用内置 imagegen 生成，提示词：

> Photorealistic editorial photograph of a calm Hangzhou boutique hotel bedroom: white linen double bed on left, warm wooden headboard, small warm bedside lamp, large window on right looking out at lush green trees. Soft natural morning light, warm cream, wood and sage green palette. Landscape 3:2, clear large shapes for a small thumbnail. No people, text, logos or watermark.

原始生成图保留在 Codex generated_images 中；网站使用压缩后的项目内 WebP，无外部图片依赖。
