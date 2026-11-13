# 住宿推荐参考图

使用内置 imagegen 生成，并压缩为 WebP（1280 × 512）。图片用于无实拍素材的旅行住宿片区卡片，均为通用氛围示意，不表示真实酒店、目的地或可订房态。沿用项目现有的本地静态资源与 HTML 内嵌图片机制，无新增依赖。

资源：

- `travelmate/images/lodging-room.webp`：湖景客房。
- `travelmate/images/lodging-city.webp`：城市街区。
- `travelmate/images/lodging-canal.webp`：水岸街区。

按卡片顺序循环使用上述素材，真实行程仍来自保存的方案。已有风景与城市参考图继续服务其他旅游内容。旧版住宿文字完整保留；新方案使用片区名及适合谁、出行便利、需要取舍、参考预算、标签五项文字。无法识别的格式整段保留，不推断房价。

生成提示词（内置工具，透明背景关闭）：

## 湖景客房

Use case: photorealistic-natural. Create one wide landscape travel editorial photograph for a travel planning website accommodation fallback image. A warm inviting boutique hotel room with neatly made ivory bed on left, natural oak furniture, subtle linen curtains, and a large window on the right overlooking a tranquil lake, lush green hills and distant traditional Chinese waterfront buildings. Tasteful understated interior, natural afternoon light, sage greens, warm cream, amber accents, authentic photographic detail. Compose for a wide 2.5:1 crop, bed and lake both visible in the middle horizontal band. This is a generic inspirational accommodation scene, no identifiable hotel, no people, no text, no logos, no watermark. Save the image as an asset and report its saved local path if available.

## 城市街区

Use case: photorealistic-natural. Asset type: wide travel accommodation area fallback photograph, 2.5:1 crop. Editorial architecture photography of an elegant modern Chinese city neighborhood, low-rise cream stone boutique hotel with warm glowing windows, tree lined boulevard, a few distant contemporary towers, late afternoon blue sky and soft golden light. Sage greens and warm cream palette, refined realistic travel magazine style, no people in foreground. Center main buildings in middle horizontal band for wide cropping. Generic destination, no recognizable real hotel, no text, logos, signs or watermark. Provide saved local asset path if available.

## 水岸街区

Use case: photorealistic-natural. Asset type: wide travel accommodation neighborhood fallback photograph, composed for 2.5:1 crop. Beautiful tranquil canal in a generic Chinese historic waterfront neighborhood, white plaster traditional houses with dark gray tiled roofs along right bank, small arched stone bridge in middle distance, willow trees on left, water reflections, warm golden evening light, realistic refined travel magazine photography. Muted greens, warm cream, restrained orange lanterns. Main buildings and bridge in central horizontal band. Generic inspirational scene, not a verified destination photograph. No text, logos, watermark, no foreground people. Provide saved local asset path if available.
