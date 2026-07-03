from config import client


def ask(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature=0.4,
    max_tokens=4000,
):
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content
