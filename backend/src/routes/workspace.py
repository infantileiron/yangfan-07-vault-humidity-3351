from fastapi import APIRouter, Depends

from src.business.profile import PROFILE
from src.controllers import workspace
from src.routes.dependencies import analyst, current_account, reviewer
from src.schemas.requests import CalibrationRequest, Import, ReviewRequest, RunRequest
from src.services import audit, calibrations, datasets, exports, reviews, runs

router = APIRouter(dependencies=[Depends(current_account)])


@router.get("/profile")
def profile():
    return PROFILE


@router.get("/datasets")
def list_datasets():
    return datasets.list_datasets()


@router.post("/datasets")
def import_dataset(body: Import, account=Depends(analyst)):
    return datasets.ingest(body.name, body.csv, account.email)


router.add_api_route("/datasets/{dataset_id}", workspace.dataset_details, methods=["GET"])
router.add_api_route("/datasets/{dataset_id}/csv", workspace.dataset_csv, methods=["GET"])


@router.get("/runs")
def list_runs():
    return runs.list_runs()


@router.post("/runs", status_code=202)
def queue_run(body: RunRequest, account=Depends(analyst)):
    return runs.submit(body, account.email)


router.add_api_route("/runs/{run_id}", workspace.run_details, methods=["GET"])
router.add_api_route("/runs/{run_id}/csv", exports.download, methods=["GET"])
router.add_api_route("/runs/{run_id}/handoff.csv", exports.signed_download, methods=["GET"])


@router.get("/calibrations")
def list_calibrations():
    return calibrations.list_calibrations()


@router.post("/calibrations", status_code=201)
def create_calibration(body: CalibrationRequest, account=Depends(analyst)):
    return calibrations.create(body, account.email)


router.add_api_route("/calibrations/{calibration_id}", workspace.calibration_details, methods=["GET"])
router.add_api_route("/recheck-rooms", workspace.recheck_rooms, methods=["GET"])


@router.post("/runs/{run_id}/review", status_code=201)
def review_run(run_id: str, body: ReviewRequest, account=Depends(reviewer)):
    return reviews.sign(run_id, body, account.email)


router.add_api_route("/reviews", reviews.list_reviews, methods=["GET"])
router.add_api_route("/audit", audit.recent, methods=["GET"])
