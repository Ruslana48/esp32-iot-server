import requests

from config import BOT_TOKEN

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_URL = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

TIMEOUT = 30

def send_message(chat_id: str, text: str) -> None:
    if not BOT_TOKEN:
        print("BOT_TOKEN is not set", flush=True)
        return
    try:
        requests.post(
            f"{API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"sendMessage failed: {exc}", flush=True)

def send_chat_action(chat_id: str, action: str = "typing") -> None:
    if not BOT_TOKEN:
        return
    try:
        requests.post(
            f"{API_URL}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        pass

def download_file(file_id: str) -> bytes:
    meta = requests.get(
        f"{API_URL}/getFile", params={"file_id": file_id}, timeout=TIMEOUT
    )
    meta.raise_for_status()
    payload = meta.json()

    if not payload.get("ok"):
        raise RuntimeError(f"getFile failed: {payload}")

    file_path = payload["result"]["file_path"]

    content = requests.get(f"{FILE_URL}/{file_path}", timeout=TIMEOUT)
    content.raise_for_status()
    return content.content