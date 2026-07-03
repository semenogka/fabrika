import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False


try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


load_dotenv()


YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
YANDEX_BASE_URL = os.getenv("YANDEX_BASE_URL", "")
YANDEX_MODEL = os.getenv("YANDEX_MODEL", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "")
GPT_MODEL = os.getenv("GPT_MODEL", "")

# Backward-compatible alias used by the existing pipeline.
FOLDER_ID = YANDEX_FOLDER_ID


class _MissingClient:
    def __getattr__(self, _name):
        raise RuntimeError(
            "Yandex API client is unavailable. Install dependencies from requirements.txt "
            "and configure .env with YANDEX_API_KEY, YANDEX_FOLDER_ID, YANDEX_BASE_URL "
            "and model names."
        )


def _build_client():
    if OpenAI is None:
        return _MissingClient()
    if not YANDEX_API_KEY or not YANDEX_BASE_URL:
        return _MissingClient()

    return OpenAI(
        api_key=YANDEX_API_KEY,
        base_url=YANDEX_BASE_URL,
    )


client = _build_client()
