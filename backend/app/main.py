from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.apis import devices, power, alert, websocket, summary
from app.database.database import SessionLocal
from app.services import energy_service
from app.services.simulator import simulator
from app.services.alert_scheduler import scheduler


app = FastAPI(title="Smart Office Energy Monitoring")

# Allow the frontend dev server (Vite) to call REST endpoints during development.
# We explicitly allow common local dev origins; adjust if your dev server uses
# a different host/port or deploy to production with a stricter policy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(devices.router)
app.include_router(power.router)
app.include_router(alert.router)
app.include_router(websocket.router)
app.include_router(summary.router)


@app.on_event("startup")
async def startup_event():
    # Record the t0 boundary (time + current total power) that energy
    # calculations integrate from. Must happen before the simulator can
    # toggle a device, so start it after this.
    db = SessionLocal()
    try:
        energy_service.initialize_baseline(db)
    finally:
        db.close()

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
