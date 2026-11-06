"""Voice intake: audio to text only.

The transcript goes back to the page for the user to confirm or edit. It never
reaches the planner on its own, so a misheard place name is always correctable
before /chat sees anything.
"""
import os
import tempfile

import httpx

# 35 个常见地名：15 个城市 + 20 个景点。既作为识别提示词，也用于事后纠错。
HOTWORDS = (
    "北京", "上海", "杭州", "成都", "西安", "厦门", "泉州", "广州", "重庆", "南京",
    "苏州", "青岛", "长沙", "昆明", "哈尔滨",
    "鼓浪屿", "故宫博物院", "西湖", "兵马俑", "宽窄巷子", "洪崖洞", "回民街", "拙政园",
    "中山陵", "亚龙湾", "石林", "栈桥", "八大关", "曾厝垵", "环岛路", "清源山",
    "开元寺", "西街", "外滩", "迪士尼乐园",
)

MAX_BYTES = 8 * 1024 * 1024
MIN_BYTES = 1024
AUDIO_SUFFIX = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
                "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav"}
# 三个字的词错一个字还能回来；两个字的词（北京/南京）错一个字就是另一个地方，宁可不纠。
SHORTEST_CORRECTABLE = 3
THRESHOLD = 0.66
_local_model = None


class VoiceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def audio_suffix(content_type):
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind not in AUDIO_SUFFIX:
        raise VoiceError("请用浏览器录音后上传音频；支持 webm、ogg、mp4、wav、mp3。", 415)
    return AUDIO_SUFFIX[kind]


def prompt_text():
    return "旅行目的地和景点：" + "、".join(HOTWORDS) + "。"


def language_value():
    return (os.getenv("ASR_LANGUAGE") or "zh").strip() or None


def _mismatches(window, word):
    return sum(1 for left, right in zip(window, word) if left != right)


def _one_shorter(shorter, word):
    return any(word[:index] + word[index + 1:] == shorter for index in range(len(word)))


def _score(window, word):
    """同长度错一两个字、或正好少一个字，才算同一个地名；否则不改，免得吞掉相邻的字。"""
    if window == word:
        return 1.0
    size = len(word)
    if len(window) == size:
        wrong = _mismatches(window, word)
        return 1 - wrong / (size * 2) if wrong <= (1 if size <= 4 else 2) else 0.0
    if len(window) == size - 1 and _one_shorter(window, word):
        return 0.8
    return 0.0


def correct(text, hotwords=HOTWORDS, threshold=THRESHOLD):
    """按热词表把听错的地名改回来；只改三个字以上的词，避免把北京改成南京。"""
    if not text:
        return text, []
    expected = sorted({word for word in hotwords if len(word) >= SHORTEST_CORRECTABLE},
                      key=len, reverse=True)
    output, fixes, index = [], [], 0
    while index < len(text):
        match = None
        for word in expected:
            size = len(word)
            for width in (size, size - 1):
                if width < SHORTEST_CORRECTABLE or index + width > len(text):
                    continue
                ratio = _score(text[index:index + width], word)
                if ratio >= threshold and (match is None or ratio > match[2]):
                    match = (width, word, ratio)
            if match and match[2] == 1.0:
                break
        if match is None:
            output.append(text[index])
            index += 1
            continue
        width, word, ratio = match
        if ratio < 1:
            fixes.append({"from": text[index:index + width], "to": word, "score": round(ratio, 2)})
        output.append(word)
        index += width
    return "".join(output), fixes


def provider():
    name = (os.getenv("ASR_PROVIDER") or "").strip().lower()
    if name in ("openai", "local"):
        return name
    # 有云端密钥就走免费额度，没有就在本地跑，两种情况都不产生额外费用。
    return "openai" if os.getenv("ASR_API_KEY") else "local"


def transcribe(audio, content_type):
    suffix = audio_suffix(content_type)
    if len(audio) < MIN_BYTES:
        raise VoiceError("录音太短，请说完一整句再停止。", 400)
    if len(audio) > MAX_BYTES:
        raise VoiceError("录音超过 8MB，请控制在 60 秒以内。", 413)
    kind = provider()
    raw = _openai(audio, suffix) if kind == "openai" else _local(audio, suffix)
    raw = " ".join(str(raw or "").split())
    if not raw:
        raise VoiceError("没有识别到语音内容，请靠近话筒重说一遍。", 422)
    text, fixes = correct(raw)
    return {"text": text, "raw": raw, "corrections": fixes, "provider": kind}


def _openai(audio, suffix):
    key = os.getenv("ASR_API_KEY")
    if not key:
        raise VoiceError("未配置语音识别：在 .env 填写 ASR_API_KEY（免费额度即可），"
                         "或安装 faster-whisper 后设 ASR_PROVIDER=local 做本地识别。", 503)
    base = (os.getenv("ASR_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("ASR_MODEL") or "whisper-1"
    optional = {"response_format": "json"}
    language = language_value()
    if language:
        optional["language"] = language
    if os.getenv("ASR_PROMPT", "1") != "0":
        # Whisper 系接口支持用 prompt 提示地名；不支持的就靠事后纠错。
        optional["prompt"] = prompt_text()
    # 硅基流动 SenseVoice 这类接口只认 file + model，多传参数直接 400，所以带一次降级重试。
    attempts = [{"model": model, **optional}, {"model": model}]
    mimetype = next((kind for kind, ext in AUDIO_SUFFIX.items() if ext == suffix),
                    "application/octet-stream")
    for index, data in enumerate(attempts):
        try:
            response = httpx.post(base + "/audio/transcriptions",
                                  headers={"Authorization": "Bearer " + key}, data=data,
                                  files={"file": ("voice" + suffix, audio, mimetype)},
                                  timeout=float(os.getenv("ASR_TIMEOUT") or 30))
            response.raise_for_status()
            return (response.json() or {}).get("text", "")
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status in (401, 403):
                raise VoiceError("语音识别的 API Key 无效或无权限，请检查 .env 的 ASR_API_KEY。", 502) from None
            if status in (400, 415, 422) and index == 0:
                continue
            if status == 429:
                raise VoiceError("语音识别触发限流，请稍后重试或改用文字输入。", 503) from None
            if status in (400, 415, 422):
                raise VoiceError("识别接口不接受这段音频（浏览器录的是 webm/opus）。"
                                 "可换支持 webm 的接口，或安装 faster-whisper 设 ASR_PROVIDER=local。", 502) from None
            raise VoiceError("语音识别服务暂时不可用，请直接输入文字或稍后重试。", 502) from None
        except (httpx.HTTPError, ValueError, TypeError):
            raise VoiceError("语音识别服务暂时不可用，请直接输入文字或稍后重试。", 502) from None


def _local(audio, suffix):
    global _local_model
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise VoiceError("本站还没开通语音识别：安装 faster-whisper 后设 ASR_PROVIDER=local，"
                         "或在 .env 填写 ASR_API_KEY 走云端免费额度。", 503) from None
    if _local_model is None:
        _local_model = WhisperModel(os.getenv("ASR_LOCAL_MODEL") or "small",
                                    device="cpu", compute_type="int8")
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio)
            path = handle.name
        segments, _ = _local_model.transcribe(path, language=language_value(), vad_filter=True,
                                             initial_prompt=prompt_text())
        return "".join(segment.text for segment in segments)
    except Exception:
        raise VoiceError("本地语音识别失败，请重试或改用文字输入。", 500) from None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
