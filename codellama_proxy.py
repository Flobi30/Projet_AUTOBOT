from openai_proxy import create_app
from fastapi import FastAPI

app: FastAPI = create_app(
    upstream_url="http://localhost:11434/v1",
    override_model="codellama:13b",
    port=11435
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11435)
