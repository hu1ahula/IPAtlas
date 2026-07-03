from ipaddress import AddressValueError, NetmaskValueError

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_repository
from app.api.schemas import BatchLookupRequest, RangeLookupRequest
from app.core.config import get_settings
from app.core.security import require_admin
from app.intel.repository import InMemoryIntelRepository
from app.tasks.update import SourceUpdateError, update_source_from_local_file

router = APIRouter()


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(repository: InMemoryIntelRepository = Depends(get_repository)) -> dict:
    from app.core.readiness import check_database, check_redis

    db_status = check_database()
    redis_status = check_redis()
    return {
        "status": "ok" if repository.record_count > 0 else "degraded",
        "index": {"ok": repository.record_count > 0, "record_count": repository.record_count},
        "geo_backend": repository.geo_status(),
        "database": db_status,
        "redis": redis_status,
    }


@router.get("/v1/ip/{ip}")
def lookup_ip(
    ip: str,
    include_sources: bool = Query(default=False),
    repository: InMemoryIntelRepository = Depends(get_repository),
) -> dict:
    try:
        return repository.lookup_ip(ip, include_sources=include_sources)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/v1/ip/batch")
def lookup_ip_batch(
    request: BatchLookupRequest,
    repository: InMemoryIntelRepository = Depends(get_repository),
) -> dict:
    max_size = get_settings().batch_max_size
    if len(request.ips) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"batch size must be <= {max_size}",
        )

    results = []
    for value in request.ips:
        try:
            results.append(repository.lookup_ip(value, include_sources=request.include_sources))
        except ValueError as exc:
            results.append({"ip": value, "found": False, "error": str(exc)})
    return {"count": len(results), "results": results}


@router.get("/v1/cidr/{cidr:path}")
def lookup_cidr(
    cidr: str,
    repository: InMemoryIntelRepository = Depends(get_repository),
) -> dict:
    try:
        return repository.query_cidr(cidr)
    except (ValueError, AddressValueError, NetmaskValueError) as exc:
        raise _bad_request(exc) from exc


@router.post("/v1/range")
def lookup_range(
    request: RangeLookupRequest,
    repository: InMemoryIntelRepository = Depends(get_repository),
) -> dict:
    try:
        return repository.query_range(request.start_ip, request.end_ip)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/v1/asn/{asn}")
def lookup_asn(asn: int, repository: InMemoryIntelRepository = Depends(get_repository)) -> dict:
    if asn < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ASN must be positive")
    return repository.query_asn(asn)


@router.get("/v1/meta/sources")
def list_sources(repository: InMemoryIntelRepository = Depends(get_repository)) -> dict:
    return {"sources": repository.sources()}


@router.post("/v1/admin/update/{source_name}")
def update_source(
    source_name: str,
    checksum: str | None = Query(default=None),
    _admin: None = Depends(require_admin),
    repository: InMemoryIntelRepository = Depends(get_repository),
) -> dict:
    try:
        return update_source_from_local_file(repository, source_name, expected_checksum=checksum)
    except SourceUpdateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
