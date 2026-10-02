from fastapi import FastAPI

app = FastAPI(title="LifeOps API")


@app.get("/health")
def health():
    return {"status": "ok"}
