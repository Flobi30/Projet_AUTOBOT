
from fastapi import FastAPI, Request
from pydantic import BaseModel
import uvicorn
import requests

app = FastAPI()

OLLAMA_LLAMA3_URL = "http://localhost:11434/api/generate"
OLLAMA_CODELLAMA_URL = "http://localhost:11435/api/generate"

class Message(BaseModel):
    role: str
    content: str

class CompletionRequest(BaseModel):
    model: str
    messages: list[Message]

@app.post("/v1/chat/completions")
async def chat_completions(request: CompletionRequest):
    prompt = request.messages[-1].content
    model = "llama3" if not any(x in prompt.lower() for x in ["code", "fonction", "def ", "class "]) else "codellama:13b"
    url = OLLAMA_LLAMA3_URL if model == "llama3" else OLLAMA_CODELLAMA_URL

    response = requests.post(url, json={
        "model": model,
        "prompt": prompt,
        "stream": False
    })

    if response.status_code != 200:
        return {"error": response.text}

    output = response.json().get("response", "")
    return {
        "id": "chatcmpl-custom",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": output},
            "finish_reason": "stop"
        }],
        "model": model
    }

if __name__ == "__main__":
    uvicorn.run("autobot_router_api:app", host="0.0.0.0", port=11436, reload=True)
