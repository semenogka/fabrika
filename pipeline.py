from config import DEEPSEEK_MODEL, FOLDER_ID, QWEN_MODEL, YANDEX_MODEL, client
from prompts import CRITIC_SYSTEM, FINAL_SYSTEM, HYPOTHESIS_SYSTEM, KPI_SYSTEM, LITERATURE_SYSTEM


def _model_uri(model_name):
    if not FOLDER_ID:
        raise RuntimeError("YANDEX_FOLDER_ID is not configured.")
    if not model_name:
        raise RuntimeError("Model name is not configured in .env.")
    return f"gpt://{FOLDER_ID}/{model_name}"


def analyze_kpi(kpi):
    return client.responses.create(
        model=_model_uri(YANDEX_MODEL),
        temperature=0.3,
        instructions=KPI_SYSTEM,
        input=kpi,
        max_output_tokens=500,
    )


def analyze_articles(parsed, text):
    return client.responses.create(
        model=_model_uri(DEEPSEEK_MODEL),
        temperature=0.3,
        instructions=LITERATURE_SYSTEM,
        input=f"{parsed}\n\n{text}",
        max_output_tokens=4000,
    )


def generate_hypothesis(data):
    return client.responses.create(
        model=_model_uri(DEEPSEEK_MODEL),
        temperature=0.3,
        instructions=HYPOTHESIS_SYSTEM,
        input=data,
        max_output_tokens=4000,
    )


def review(hypothesis):
    return client.responses.create(
        model=_model_uri(DEEPSEEK_MODEL),
        temperature=0.3,
        instructions=CRITIC_SYSTEM,
        input=hypothesis,
        max_output_tokens=4000,
    )


def explain(data):
    return client.responses.create(
        model=_model_uri(YANDEX_MODEL),
        temperature=0.3,
        instructions=FINAL_SYSTEM,
        input=data,
        max_output_tokens=4000,
    )
