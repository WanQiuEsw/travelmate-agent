"""语音识别配置自检：打印生效配置 → 发一段测试音频 → 按返回码给出下一步。

    .venv/Scripts/python.exe scripts/check_asr.py
    .venv/Scripts/python.exe scripts/check_asr.py --file 你的录音.webm

不带 --file 时用一段 1.2 秒静音 wav 探测：静音本来就没有内容，只要接口不报鉴权或
格式错误，就说明 .env 配对了。想看真实识别效果就传自己的录音。
"""
import argparse
import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from travelmate import asr  # noqa: E402


def mask(value):
    if not value:
        return "（空）"
    return value[:6] + "…" + value[-4:] if len(value) > 12 else value[:3] + "…"


def silence_wav(seconds=1.2, rate=16000):
    """16kHz 单声道 16bit 静音 wav，够过 MIN_BYTES 也不含任何语音。"""
    samples = int(rate * seconds)
    data = b"\x00\x00" * samples
    header = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
              + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
              + b"data" + struct.pack("<I", len(data)))
    return header + data


def report_config():
    provider = asr.provider()
    base = (os.getenv("ASR_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("ASR_MODEL") or "whisper-1"
    key = (os.getenv("ASR_API_KEY") or "").strip()
    print("当前生效配置：")
    print(f"  ASR_PROVIDER = {provider}")
    print(f"  ASR_BASE_URL = {base}")
    print(f"  ASR_MODEL    = {model}")
    print(f"  ASR_API_KEY  = {mask(key)}")
    print(f"  ASR_LANGUAGE = {asr.language_value() or '（不传）'}")
    print(f"  提示词        = {'开' if os.getenv('ASR_PROMPT', '1') != '0' else '关'}，热词 {len(asr.HOTWORDS)} 条")
    problems = []
    if provider == "local":
        problems.append("当前是本地识别（ASR_PROVIDER=local）：需要 faster-whisper，本脚本不测本地路径。")
    else:
        if not key:
            problems.append("ASR_API_KEY 为空：云端接口一定 401，先填 Key。")
        elif not key.startswith("sk-"):
            problems.append("ASR_API_KEY 不像硅基流动的 Key（正常以 sk- 开头），确认没粘错。")
    if "siliconflow.com" in base:
        problems.append("域名写成了 api.siliconflow.com：应为 .cn，否则正确 Key 也会 401 Token is invalid。")
    if base.endswith("/audio/transcriptions"):
        problems.append("ASR_BASE_URL 只写到 /v1 就行，不要再带 /audio/transcriptions（会和代码拼接重复）。")
    if "siliconflow" in base and "SenseVoice" not in model and "TeleSpeech" not in model:
        problems.append(f"硅基流动的语音模型是 FunAudioLLM/SenseVoiceSmall 或 TeleAI/TeleSpeechASR，"
                        f"当前 ASR_MODEL={model} 可能不存在。")
    if "openai.com" in base and not model.startswith("whisper"):
        problems.append(f"OpenAI 的语音模型是 whisper-1，当前 ASR_MODEL={model}。")
    for problem in problems:
        print("  ⚠ " + problem)
    return provider, problems


def main():
    load_dotenv(Path.cwd() / ".env", encoding="utf-8-sig")
    parser = argparse.ArgumentParser(description="检查语音识别配置")
    parser.add_argument("--file", help="用这段录音做真实识别（默认发一段静音探测）")
    options = parser.parse_args()

    provider, problems = report_config()
    print()
    if provider == "local":
        print("跳过云端检查。要本地识别：pip install faster-whisper 后直接点页面上的语音按钮。")
        return 1 if problems else 0

    if options.file:
        audio = Path(options.file).read_bytes()
        suffix = Path(options.file).suffix.lower()
        content_type = next((kind for kind, ext in asr.AUDIO_SUFFIX.items() if ext == suffix), "")
        source = options.file
    else:
        audio = silence_wav()
        content_type, source = "audio/wav", "内置 1.2 秒静音 wav"

    print(f"发送 {source}（{len(audio) / 1024:.1f} KB，Content-Type: {content_type}）…")
    try:
        result = asr.transcribe(audio, content_type)
    except asr.VoiceError as error:
        if "没有识别到语音内容" in error.message:
            print("✅ 通了：鉴权、域名、模型、音频格式都正常；静音没有内容，所以没文字。")
            print("   想确认识别效果，用 --file 传一段真人录音再跑一次。")
            return 0
        print(f"❌ {error.message}")
        print("   对照上面的 ⚠ 逐条改 .env，改完要重启服务再跑一次。")
        return 1
    except Exception as error:  # 网络层异常直接暴露，别吞
        print(f"❌ 调用异常：{type(error).__name__}: {error}")
        return 1

    print(f"✅ 识别成功（provider={result['provider']}）")
    print(f"   原文：{result['raw']}")
    print(f"   纠正后：{result['text']}")
    if result["corrections"]:
        print("   热词纠错：" + "；".join(f"{item['from']} → {item['to']}" for item in result["corrections"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
