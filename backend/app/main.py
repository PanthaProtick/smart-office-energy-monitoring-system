from fastapi import FastAPI

from app.apis import devices, power, alert, websocket
from app.services.simulator import simulator
from app.services.alert_scheduler import scheduler


app = FastAPI(title="Smart Office Energy Monitoring")


app.include_router(devices.router)
app.include_router(power.router)
app.include_router(alert.router)
app.include_router(websocket.router)


@app.on_event("startup")
async def startup_event():
    await simulator.start()
    await scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    await simulator.stop()
    await scheduler.stop()


@app.get("/")
def root():
    return {"status": "ok"}


if __name__ == "__main__":
    # lightweight way to run when invoked directly (use uvicorn in prod/dev)
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
