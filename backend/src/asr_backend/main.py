from fastapi import FastAPI

app = FastAPI(title="Automatic Systematic Review API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
