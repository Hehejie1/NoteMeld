from fastapi import APIRouter

from app.services.usage import UsageService
from app.utils.response import ResponseWrapper as R

router = APIRouter(prefix="/usage")


@router.get("/overview")
def usage_overview(
    start_at: str | None = None,
    end_at: str | None = None,
    task_id: str | None = None,
    provider_id: str | None = None,
    model_name: str | None = None,
    status: str | None = None,
):
    return R.success(
        UsageService.get_overview(
            start_at=start_at,
            end_at=end_at,
            task_id=task_id,
            provider_id=provider_id,
            model_name=model_name,
            status=status,
        )
    )


@router.get("/records")
def usage_records(
    start_at: str | None = None,
    end_at: str | None = None,
    task_id: str | None = None,
    provider_id: str | None = None,
    model_name: str | None = None,
    status: str | None = None,
):
    return R.success(
        UsageService.get_records(
            start_at=start_at,
            end_at=end_at,
            task_id=task_id,
            provider_id=provider_id,
            model_name=model_name,
            status=status,
        )
    )


@router.get("/task_summary")
def usage_task_summary(
    start_at: str | None = None,
    end_at: str | None = None,
    task_id: str | None = None,
    provider_id: str | None = None,
    model_name: str | None = None,
):
    return R.success(
        UsageService.get_task_summary(
            start_at=start_at,
            end_at=end_at,
            task_id=task_id,
            provider_id=provider_id,
            model_name=model_name,
        )
    )


@router.get("/task_calls/{task_id}")
def usage_task_calls(task_id: str):
    return R.success(UsageService.get_task_calls(task_id))
