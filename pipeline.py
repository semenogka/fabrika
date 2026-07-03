from llm import ask
from config import *

from prompts import *

def analyze_kpi(kpi):

    return client.responses.create(
        model=f"gpt://{FOLDER_ID}/{YANDEX_MODEL}",
        temperature=0.3,
        instructions=KPI_SYSTEM,
        input=kpi,
        max_output_tokens=500
    )

def analyze_articles(parsed, text):

    return client.responses.create(
        model=f"gpt://{FOLDER_ID}/{QWEN_MODEL}",
        temperature=0.3,
        instructions=LITERATURE_SYSTEM,
        input=parsed + text,
        max_output_tokens=4000
    )

def generate_hypothesis(data):

    return client.responses.create(
	model=f"gpt://{FOLDER_ID}/{DEEPSEEK_MODEL}",
	temperature=0.3,
	instructions=HYPOTHESIS_SYSTEM,
	input=data,
	max_output_tokens=4000
)

def review(hypothesis):

    return client.responses.create(
        model=f"gpt://{FOLDER_ID}/{DEEPSEEK_MODEL}",
        temperature=0.3,
        instructions=CRITIC_SYSTEM,
        input=hypothesis,
        max_output_tokens=4000
    )

def explain(data):

    return client.responses.create(
        model=f"gpt://{FOLDER_ID}/{YANDEX_MODEL}",
        temperature=0.3,
        instructions=FINAL_SYSTEM,
        input=data,
        max_output_tokens=4000
    )