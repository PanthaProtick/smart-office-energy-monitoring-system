from fastapi import FastAPI

from app.apis import devices, power, alert


app = FastAPI(title="Smart Office Energy Monitoring")


app.include_router(devices.router)
app.include_router(power.router)
app.include_router(alert.router)


@app.get("/")
def root():
    return {"status": "ok"}


if __name__ == "__main__":
    # lightweight way to run when invoked directly (use uvicorn in prod/dev)
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
