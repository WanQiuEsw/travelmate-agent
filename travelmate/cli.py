import argparse
from uuid import uuid4

from travelmate.agent import chat, open_agent


def main():
    parser = argparse.ArgumentParser(description="TravelMate 旅游助手，输入 /exit 退出")
    parser.add_argument("--session", default=None, help="复用此 ID 继续历史对话")
    args = parser.parse_args()
    session = args.session or str(uuid4())
    print(f"会话：{session}")
    try:
        with open_agent() as agent:
            while True:
                message = input("你：").strip()
                if message == "/exit":
                    break
                if not message:
                    continue
                if len(message) > 8000:
                    print("消息最多 8000 字符")
                    continue
                try:
                    print("TravelMate：", chat(agent, session, message))
                except Exception:
                    print("请求失败，请检查模型配置或网络。可使用同一会话重试。")
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    except (EOFError, KeyboardInterrupt):
        print()


if __name__ == "__main__":
    main()
