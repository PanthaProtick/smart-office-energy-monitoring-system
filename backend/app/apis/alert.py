from fastapi import APIRouter

router = APIRouter()


@router.get("/alerts")
def get_alerts():
	# placeholder for alerting rules
	return {"alerts": []}

