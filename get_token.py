"""Get a Yandex Music OAuth token via Device Flow and save it to .env.

Prints a verification URL + short code. Open the URL, enter the code, confirm.
The token is then written into YANDEX_MUSIC_TOKEN in .env automatically.
"""
import re
import sys

import config


def _on_code(code):
    print(f"VERIFY_URL={code.verification_url}", flush=True)
    print(f"USER_CODE={code.user_code}", flush=True)
    print("Waiting for you to authorize on Yandex...", flush=True)


def _save_token(token: str) -> None:
    env_path = config.ROOT / ".env"
    text = env_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^YANDEX_MUSIC_TOKEN=.*$", text):
        text = re.sub(r"(?m)^YANDEX_MUSIC_TOKEN=.*$",
                      f"YANDEX_MUSIC_TOKEN={token}", text)
    else:
        text += f"\nYANDEX_MUSIC_TOKEN={token}\n"
    env_path.write_text(text, encoding="utf-8")


def main():
    from yandex_music import Client

    token = Client().device_auth(on_code=_on_code, timeout=300)
    if not token or not token.access_token:
        sys.exit("No token returned (timed out or declined).")
    _save_token(token.access_token)
    print(f"TOKEN_SAVED prefix={token.access_token[:6]}... len={len(token.access_token)}")


if __name__ == "__main__":
    main()
