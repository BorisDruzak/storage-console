"""Admin-only explicit derived rechecks; no confidence input or source mutation."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from apps.api.ingest import ApiError
from apps.api.user_auth.dependencies import require_csrf, require_permission
from apps.api.user_auth.sessions import Actor
from packages.contracts.audit import AuditRecheck, AuditRecheckRequest
from packages.shared.audit.correlation import RULE_VERSION
from packages.shared.audit.recheck import ChangeNotFound, RecheckConflict, request

Admin = Annotated[Actor, Depends(require_permission("manage_sources"))]


def router(engine: Engine) -> APIRouter:
    result = APIRouter(
        prefix="/api/v1/audit",
        tags=["audit-control"],
        dependencies=[
            Depends(require_permission("read_sensitive_activity")),
            Depends(require_csrf),
        ],
        responses={code: {"model": ApiError} for code in (401, 403, 404, 409, 413, 422, 503)},
    )

    @result.post("/changes/{change_id}/recheck", status_code=202)
    def recheck(
        change_id: UUID, data: AuditRecheckRequest, actor: Admin, response: Response
    ) -> AuditRecheck:
        response.headers["Cache-Control"] = "no-store"
        if data.rule_version != RULE_VERSION:
            raise HTTPException(
                409, "AUDIT_RULE_VERSION_CHANGED", headers={"Cache-Control": "no-store"}
            )
        try:
            with engine.begin() as connection:
                row = request(connection, change_id, actor.id)
                return AuditRecheck(
                    change_id=change_id,
                    job_id=row["id"],
                    rule_version=RULE_VERSION,
                    status=row["status"],
                    requested_at=row["created_at"],
                )
        except ChangeNotFound:
            raise HTTPException(
                404, "CHANGE_NOT_FOUND", headers={"Cache-Control": "no-store"}
            ) from None
        except RecheckConflict:
            raise HTTPException(
                409, "AUDIT_RECHECK_CONFLICT", headers={"Cache-Control": "no-store"}
            ) from None
        except SQLAlchemyError:
            raise HTTPException(
                503, "AUDIT_CONTROL_UNAVAILABLE", headers={"Cache-Control": "no-store"}
            ) from None

    return result
