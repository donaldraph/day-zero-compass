import os
from openai import OpenAI

client = OpenAI(base_url="https://models.github.ai/inference", api_key=os.environ["GITHUB_TOKEN"])
resp = client.chat.completions.create(model="openai/gpt-4o", messages=[{"role": "user", "content": "Say OK"}], max_tokens=10)
print(resp.model, "->", resp.choices[0].message.content)
