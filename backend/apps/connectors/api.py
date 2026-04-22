import logging
import secrets
from urllib.parse import quote, urlencode
from uuid import UUID

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.shortcuts import redirect
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.auth import api_or_session
from apps.accounts.permissions import check_role, require_role
from apps.common.throttles import (
    AiExtractionThrottle,
    CreateAuthThrottle,
    MutationThrottle,
    ReadThrottle,
    WebhookThrottle,
)
from apps.connectors.enums import (
    CandidateStatus,
    CredentialStatus,
    ProviderChoices,
    SyncJobStatus,
    SyncJobType,
)
from apps.connectors.models import (
    CandidateSource,
    CaptureCandidate,
    ConnectorCredential,
    ExtractionJob,
    SyncedPage,
    SyncJob,
)
from apps.orgs.enums import RoleChoices

logger = logging.getLogger(__name__)

router = Router(tags=["connectors"])

_ATLASSIAN_AUTH_URL = "https://auth.atlassian.com/authorize"
_OAUTH_CACHE_PREFIX = "oauth_state"
_OAUTH_STATE_TTL = 600  # 10 minutes


# ── Schemas ───────────────────────────────────────────────────────────────


class ConnectOut(Schema):
    redirect_url: str


class SyncJobBriefOut(Schema):
    status: str
    pages_updated: int
    finished_at: str | None


class ExtractionJobBriefOut(Schema):
    id: str
    status: str
    pages_scored: int
    pages_extracted: int
    candidates_created: int
    started_at: str | None
    finished_at: str | None


class ConnectorOut(Schema):
    id: str
    provider: str
    site_url: str
    status: str
    connected_by_email: str | None
    last_sync_job: SyncJobBriefOut | None
    last_extraction_job: ExtractionJobBriefOut | None
    synced_pages_count: int
    changed_pages_count: int
    created_at: str


class SyncedPageOut(Schema):
    id: str
    external_id: str
    external_url: str
    space_key: str
    title: str
    content_md: str | None = None
    last_synced_at: str


class PageListOut(Schema):
    items: list[SyncedPageOut]
    next_cursor: str | None


class ExtractionJobOut(Schema):
    id: str
    status: str
    pages_scored: int
    pages_extracted: int
    candidates_created: int
    error_message: str
    started_at: str | None
    finished_at: str | None
    created_at: str


class CandidateSourceBriefOut(Schema):
    id: str
    page_title: str
    page_external_url: str


class CandidateOut(Schema):
    id: str
    title: str
    slug: str
    description: str
    probability_score: float
    automation_tier: str
    automation_reasoning: str
    integration_needs: list[dict]
    status: str
    promoted_process_slug: str | None
    sources: list[CandidateSourceBriefOut] | None
    created_at: str


class CandidateListOut(Schema):
    items: list[CandidateOut]
    next_cursor: str | None
    total: int


class PromoteCandidateIn(Schema):
    department_id: str
    owner_id: str | None = None
    title: str | None = None
    description: str | None = None


class PromoteOut(Schema):
    process_slug: str


# ── Capture funnel stats ──────────────────────────────────────────────────


class CaptureFunnelOut(Schema):
    synced_pages: int
    candidates_extracted: int
    candidates_promoted: int
    has_connector: bool


@router.get(
    "/capture-stats",
    response=CaptureFunnelOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER, RoleChoices.MEMBER)
def capture_stats(request):
    workspace = request.workspace
    creds = ConnectorCredential.objects.filter(
        workspace=workspace,
    ).exclude(status=CredentialStatus.DISCONNECTED)

    if not creds.exists():
        return {
            "synced_pages": 0,
            "candidates_extracted": 0,
            "candidates_promoted": 0,
            "has_connector": False,
        }

    cred_ids = list(creds.values_list("id", flat=True))
    synced_pages = SyncedPage.objects.filter(credential_id__in=cred_ids).count()
    candidates_extracted = (
        CaptureCandidate.objects.filter(
            credential_id__in=cred_ids,
        )
        .exclude(status=CandidateStatus.DISMISSED)
        .count()
    )
    candidates_promoted = CaptureCandidate.objects.filter(
        credential_id__in=cred_ids,
        status=CandidateStatus.PROMOTED,
    ).count()

    return {
        "synced_pages": synced_pages,
        "candidates_extracted": candidates_extracted,
        "candidates_promoted": candidates_promoted,
        "has_connector": True,
    }


# ── OAuth initiate ────────────────────────────────────────────────────────


@router.get(
    "/confluence/connect",
    response=ConnectOut,
    auth=api_or_session,
    throttle=[CreateAuthThrottle()],
)
def confluence_connect(request: HttpRequest):
    workspace = request.workspace
    check_role(request, RoleChoices.ADMIN)

    nonce = secrets.token_hex(16)
    state = f"{workspace.id}|{nonce}"
    cache.set(f"{_OAUTH_CACHE_PREFIX}:{nonce}", str(workspace.id), _OAUTH_STATE_TTL)

    params = urlencode(
        {
            "audience": "api.atlassian.com",
            "client_id": settings.ATLASSIAN_CLIENT_ID,
            "scope": " ".join(settings.ATLASSIAN_OAUTH_SCOPES),
            "redirect_uri": _callback_url(),
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
    )
    return ConnectOut(redirect_url=f"{_ATLASSIAN_AUTH_URL}?{params}")


# ── OAuth callback ────────────────────────────────────────────────────────


@router.get("/confluence/callback", auth=None)
def confluence_callback(request: HttpRequest, code: str = "", state: str = "", error: str = ""):
    if error:
        return redirect(f"{settings.FRONTEND_URL}/capture/connectors?error={quote(error)}")

    parts = state.split("|", 1)
    if len(parts) != 2:
        raise HttpError(400, "Invalid state parameter")

    nonce = parts[1]
    workspace_id = cache.get(f"{_OAUTH_CACHE_PREFIX}:{nonce}")
    if not workspace_id:
        raise HttpError(400, "OAuth state expired or invalid")
    cache.delete(f"{_OAUTH_CACHE_PREFIX}:{nonce}")

    from datetime import timedelta

    from django.utils import timezone

    from apps.connectors.confluence.client import exchange_code_for_tokens, get_accessible_resources

    try:
        tokens = async_to_sync(exchange_code_for_tokens)(code, _callback_url())
    except Exception:
        logger.exception("Failed to exchange authorization code")
        raise HttpError(502, "Failed to exchange authorization code")

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    logger.info(
        "Confluence OAuth callback: token_type=%s, expires_in=%s, has_refresh=%s, scope=%s",
        tokens.get("token_type"),
        expires_in,
        bool(refresh_token),
        tokens.get("scope"),
    )

    try:
        resources = async_to_sync(get_accessible_resources)(access_token)
    except Exception:
        raise HttpError(502, "Failed to fetch accessible resources")

    if not resources:
        raise HttpError(400, "No Atlassian sites accessible with this account")

    # Use the first accessible site
    resource = resources[0]
    cloud_id = resource["id"]
    site_url = resource["url"]

    from apps.orgs.models import Workspace

    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except Workspace.DoesNotExist:
        raise HttpError(400, "Workspace not found")

    credential, _ = ConnectorCredential.objects.update_or_create(
        workspace=workspace,
        provider=ProviderChoices.CONFLUENCE,
        defaults={
            "cloud_id": cloud_id,
            "site_url": site_url,
            "token_expires_at": timezone.now() + timedelta(seconds=expires_in),
            "scopes": " ".join(settings.ATLASSIAN_OAUTH_SCOPES),
            "status": CredentialStatus.ACTIVE,
            "connected_by": request.user if request.user.is_authenticated else None,
        },
    )
    credential.set_access_token(access_token)
    if refresh_token:
        credential.set_refresh_token(refresh_token)
    credential.save(
        update_fields=[
            "access_token",
            "refresh_token",
            "cloud_id",
            "site_url",
            "token_expires_at",
            "scopes",
            "status",
            "updated_at",
        ]
    )

    # Register webhook
    callback_url = f"{settings.APP_BASE_URL}/api/v1/connectors/confluence/webhook"
    try:
        from apps.connectors.confluence.webhooks import register_webhook

        webhook_id = async_to_sync(register_webhook)(cloud_id, access_token, callback_url)
        credential.webhook_id = webhook_id
        credential.save(update_fields=["webhook_id", "updated_at"])
    except Exception:
        logger.warning("Webhook registration failed for cloud_id=%s", cloud_id, exc_info=True)

    # Enqueue initial full sync
    job = SyncJob.objects.create(
        credential=credential,
        job_type=SyncJobType.FULL,
        status=SyncJobStatus.PENDING,
    )
    from tasks import task_backend

    task_backend.enqueue(
        "confluence_full_sync",
        credential_id=str(credential.id),
        job_id=str(job.id),
    )

    return redirect(f"{settings.FRONTEND_URL}/capture/connectors?connected=confluence")


# ── List connectors ───────────────────────────────────────────────────────


@router.get(
    "/",
    response=list[ConnectorOut],
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_connectors(request: HttpRequest):
    from django.db.models import Count, F, Q

    workspace = request.workspace
    credentials = (
        ConnectorCredential.objects.filter(workspace=workspace)
        .exclude(status=CredentialStatus.DISCONNECTED)
        .select_related("connected_by")
        .annotate(
            _synced_pages_count=Count("synced_pages"),
            _changed_pages_count=Count(
                "synced_pages",
                filter=~Q(synced_pages__extraction_checksum=F("synced_pages__checksum")),
            ),
        )
        .order_by("-created_at")
    )
    cred_list = list(credentials)
    cred_ids = [c.id for c in cred_list]

    last_sync_map = {}
    last_sync_ids = (
        SyncJob.objects.filter(credential_id__in=cred_ids)
        .order_by("credential_id", "-created_at")
        .distinct("credential_id")
        .values_list("id", flat=True)
    )
    for job in SyncJob.objects.filter(id__in=last_sync_ids):
        last_sync_map[job.credential_id] = job

    last_extraction_map = {}
    last_extraction_ids = (
        ExtractionJob.objects.filter(credential_id__in=cred_ids)
        .order_by("credential_id", "-created_at")
        .distinct("credential_id")
        .values_list("id", flat=True)
    )
    for job in ExtractionJob.objects.filter(id__in=last_extraction_ids):
        last_extraction_map[job.credential_id] = job

    return [
        _build_connector_out(
            c,
            last_sync_job=last_sync_map.get(c.id),
            last_extraction_job=last_extraction_map.get(c.id),
        )
        for c in cred_list
    ]


# ── Disconnect ────────────────────────────────────────────────────────────


@router.delete(
    "/{credential_id}",
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
def disconnect_connector(request: HttpRequest, credential_id: UUID):
    workspace = request.workspace
    check_role(request, RoleChoices.ADMIN)

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    # Best-effort webhook deregistration
    if credential.provider == ProviderChoices.CONFLUENCE and credential.webhook_id:
        try:
            from apps.connectors.confluence.webhooks import deregister_webhook

            async_to_sync(deregister_webhook)(
                credential.cloud_id,
                credential.get_access_token(),
                credential.webhook_id,
            )
        except Exception:
            logger.warning(
                "Webhook deregistration failed for credential=%s", credential_id, exc_info=True
            )

    credential.status = CredentialStatus.DISCONNECTED
    credential.access_token = ""
    credential.refresh_token = ""
    credential.save(update_fields=["status", "access_token", "refresh_token", "updated_at"])
    return {"ok": True}


# ── List synced pages ─────────────────────────────────────────────────────


@router.get(
    "/{credential_id}/pages",
    response=PageListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_pages(
    request: HttpRequest,
    credential_id: UUID,
    space_key: str = "",
    search: str = "",
    cursor: str = "",
    limit: int = 50,
):
    workspace = request.workspace
    check_role(request, RoleChoices.ADMIN)

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    limit = min(limit, 200)
    qs = SyncedPage.objects.filter(credential=credential).order_by("-last_synced_at")

    if space_key:
        qs = qs.filter(space_key=space_key)
    if search:
        qs = qs.filter(title__icontains=search)
    if cursor:
        from datetime import datetime

        try:
            parsed_cursor = datetime.fromisoformat(cursor)
        except (ValueError, TypeError):
            raise HttpError(400, "Invalid cursor format; expected ISO 8601 datetime")
        qs = qs.filter(last_synced_at__lt=parsed_cursor)

    pages = list(qs[: limit + 1])
    has_more = len(pages) > limit
    items = pages[:limit]

    next_cursor = str(items[-1].last_synced_at.isoformat()) if has_more and items else None
    return PageListOut(
        items=[_build_page_out(p) for p in items],
        next_cursor=next_cursor,
    )


# ── Manual sync trigger ───────────────────────────────────────────────────


@router.post(
    "/{credential_id}/sync",
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
def trigger_sync(request: HttpRequest, credential_id: UUID):
    workspace = request.workspace
    check_role(request, RoleChoices.ADMIN)

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    if credential.status == CredentialStatus.DISCONNECTED:
        raise HttpError(400, "Connector is disconnected")

    job = SyncJob.objects.create(
        credential=credential,
        job_type=SyncJobType.FULL,
        status=SyncJobStatus.PENDING,
    )
    from tasks import task_backend

    task_backend.enqueue(
        "confluence_full_sync",
        credential_id=str(credential.id),
        job_id=str(job.id),
    )
    return {"job_id": str(job.id)}


# ── Webhook receiver ──────────────────────────────────────────────────────


_WEBHOOK_MAX_BODY_BYTES = 256 * 1024


@router.post("/confluence/webhook", auth=None, throttle=[WebhookThrottle()])
def confluence_webhook(request: HttpRequest):
    from apps.connectors.confluence.webhooks import verify_webhook_signature

    body = request.body
    if len(body) > _WEBHOOK_MAX_BODY_BYTES:
        raise HttpError(413, "Payload too large")

    signature = request.headers.get("X-Hub-Signature", "")
    if not verify_webhook_signature(body, signature):
        raise HttpError(403, "Invalid webhook signature")

    import json

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON payload")

    event = payload.get("webhookEvent", "")
    page_id = str(payload.get("page", {}).get("id", ""))

    if not page_id:
        return {"ok": True}

    # Resolve credential by cloud ID embedded in the webhook payload
    cloud_id = _extract_cloud_id(payload)
    if not cloud_id:
        return {"ok": True}

    credential = ConnectorCredential.objects.filter(
        cloud_id=cloud_id,
        provider=ProviderChoices.CONFLUENCE,
        status=CredentialStatus.ACTIVE,
    ).first()
    if not credential:
        return {"ok": True}

    if event in ("page_created", "page_updated"):
        from tasks import task_backend

        task_backend.enqueue(
            "confluence_sync_page",
            credential_id=str(credential.id),
            page_id=page_id,
        )
    elif event == "page_removed":
        SyncedPage.objects.filter(credential=credential, external_id=page_id).delete()

    return {"ok": True}


# ── Extraction trigger ───────────────────────────────────────────────────


@router.post(
    "/{credential_id}/extract",
    auth=api_or_session,
    throttle=[AiExtractionThrottle()],
)
@require_role(RoleChoices.ADMIN)
def trigger_extraction(request: HttpRequest, credential_id: UUID):
    from django.db import transaction

    workspace = request.workspace

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    if credential.status == CredentialStatus.DISCONNECTED:
        raise HttpError(400, "Connector is disconnected")

    with transaction.atomic():
        ConnectorCredential.objects.select_for_update().filter(id=credential.id).first()

        running = ExtractionJob.objects.filter(
            credential=credential,
            status__in=[SyncJobStatus.PENDING, SyncJobStatus.RUNNING],
        ).exists()
        if running:
            raise HttpError(409, "An extraction job is already in progress")

        job = ExtractionJob.objects.create(
            credential=credential,
            status=SyncJobStatus.PENDING,
        )

    from tasks import task_backend

    task_backend.enqueue(
        "capture_extract_processes",
        credential_id=str(credential.id),
        job_id=str(job.id),
    )
    return {"job_id": str(job.id)}


# ── Extraction job list ───────────────────────────────────────────────────


@router.get(
    "/{credential_id}/extraction-jobs",
    response=list[ExtractionJobOut],
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_extraction_jobs(
    request: HttpRequest,
    credential_id: UUID,
    limit: int = 10,
):
    workspace = request.workspace

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    limit = min(limit, 50)
    jobs = ExtractionJob.objects.filter(credential=credential).order_by("-created_at")[:limit]
    return [_build_extraction_job_out(j) for j in jobs]


# ── Candidates list ───────────────────────────────────────────────────────


@router.get(
    "/{credential_id}/candidates",
    response=CandidateListOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def list_candidates(
    request: HttpRequest,
    credential_id: UUID,
    status: str = "pending",
    automation_tier: str = "",
    search: str = "",
    cursor: str = "",
    limit: int = 50,
):
    workspace = request.workspace

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    limit = min(limit, 200)
    qs = CaptureCandidate.objects.filter(credential=credential).order_by("-created_at")

    if status:
        qs = qs.filter(status=status)
    if automation_tier:
        qs = qs.filter(automation_tier=automation_tier)
    if search:
        qs = qs.filter(title__icontains=search)
    if cursor:
        from datetime import datetime

        try:
            parsed_cursor = datetime.fromisoformat(cursor)
        except (ValueError, TypeError):
            raise HttpError(400, "Invalid cursor format; expected ISO 8601 datetime")
        qs = qs.filter(created_at__lt=parsed_cursor)

    total = qs.count()
    items = list(qs[: limit + 1])
    has_more = len(items) > limit
    items = items[:limit]

    next_cursor = str(items[-1].created_at.isoformat()) if has_more and items else None
    return CandidateListOut(
        items=[_build_candidate_out(c, include_sources=False) for c in items],
        next_cursor=next_cursor,
        total=total,
    )


# ── Candidate detail ──────────────────────────────────────────────────────


@router.get(
    "/{credential_id}/candidates/{candidate_id}",
    response=CandidateOut,
    auth=api_or_session,
    throttle=[ReadThrottle()],
)
def get_candidate(request: HttpRequest, credential_id: UUID, candidate_id: UUID):
    workspace = request.workspace

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    try:
        candidate = CaptureCandidate.objects.get(id=candidate_id, credential=credential)
    except CaptureCandidate.DoesNotExist:
        raise HttpError(404, "Candidate not found")

    return _build_candidate_out(candidate, include_sources=True)


# ── Promote ───────────────────────────────────────────────────────────────


@router.post(
    "/{credential_id}/candidates/{candidate_id}/promote",
    response=PromoteOut,
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN, RoleChoices.TEAM_MANAGER)
def promote_candidate(
    request: HttpRequest,
    credential_id: UUID,
    candidate_id: UUID,
    payload: PromoteCandidateIn,
):
    from django.db import transaction
    from django.utils.text import slugify

    from apps.orgs.models import Department
    from apps.processes.enums import StatusChoices, VisibilityChoices
    from apps.processes.models import Process, ProcessVersion

    workspace = request.workspace

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    try:
        candidate = CaptureCandidate.objects.get(id=candidate_id, credential=credential)
    except CaptureCandidate.DoesNotExist:
        raise HttpError(404, "Candidate not found")

    if candidate.status != CandidateStatus.PENDING:
        raise HttpError(400, f"Candidate has already been {candidate.status}")

    try:
        department = Department.objects.get(id=payload.department_id, team__workspace=workspace)
    except Department.DoesNotExist:
        raise HttpError(404, "Department not found")

    title = (payload.title or candidate.title)[:500]
    description = (payload.description or candidate.description)[:2000]

    import re as _re

    from django.db.models import IntegerField, Max
    from django.db.models.functions import Cast, Substr

    base_slug = slugify(title)[:180] or "process"
    with transaction.atomic():
        ws_processes = Process.objects.filter(department__team__workspace=workspace)
        if not ws_processes.filter(slug=base_slug).exists():
            process_slug = base_slug
        else:
            prefix = f"{base_slug}-"
            max_n = (
                (
                    ws_processes.filter(
                        slug__startswith=prefix,
                        slug__regex=rf"^{_re.escape(base_slug)}-\d+$",
                    )
                    .annotate(_suffix=Cast(Substr("slug", len(prefix) + 1), IntegerField()))
                    .aggregate(m=Max("_suffix"))["m"]
                )
                or 0
            )
            process_slug = f"{base_slug}-{max_n + 1}"

        owner = None
        if payload.owner_id:
            from apps.accounts.models import User

            owner = User.objects.filter(id=payload.owner_id).first()

        process = Process.objects.create(
            department=department,
            owner=owner or (request.user if request.user.is_authenticated else None),
            title=title,
            slug=process_slug,
            description=description,
            status=StatusChoices.DRAFT,
            visibility=VisibilityChoices.DEPARTMENT,
        )

        version = ProcessVersion.objects.create(
            process=process,
            authored_by=request.user if request.user.is_authenticated else None,
            version_number=1,
            content_md=candidate.content_md,
            frontmatter_yaml=candidate.frontmatter_yaml,
            change_summary="Promoted from Confluence via AI extraction",
        )

        process.current_version = version
        process.save(update_fields=["current_version", "updated_at"])

        candidate.status = CandidateStatus.PROMOTED
        candidate.promoted_process = process
        candidate.save(update_fields=["status", "promoted_process", "updated_at"])

    return PromoteOut(process_slug=process.slug)


# ── Dismiss ───────────────────────────────────────────────────────────────


@router.post(
    "/{credential_id}/candidates/{candidate_id}/dismiss",
    auth=api_or_session,
    throttle=[MutationThrottle()],
)
@require_role(RoleChoices.ADMIN)
def dismiss_candidate(request: HttpRequest, credential_id: UUID, candidate_id: UUID):
    workspace = request.workspace

    try:
        credential = ConnectorCredential.objects.get(id=credential_id, workspace=workspace)
    except ConnectorCredential.DoesNotExist:
        raise HttpError(404, "Connector not found")

    try:
        candidate = CaptureCandidate.objects.get(id=candidate_id, credential=credential)
    except CaptureCandidate.DoesNotExist:
        raise HttpError(404, "Candidate not found")

    if candidate.status != CandidateStatus.PENDING:
        raise HttpError(400, f"Candidate has already been {candidate.status}")

    candidate.status = CandidateStatus.DISMISSED
    candidate.save(update_fields=["status", "updated_at"])
    return {"ok": True}


# ── Helpers ───────────────────────────────────────────────────────────────


def _callback_url() -> str:
    return f"{settings.APP_BASE_URL}/api/v1/connectors/confluence/callback"


def _build_connector_out(
    credential: ConnectorCredential,
    *,
    last_sync_job: SyncJob | None = None,
    last_extraction_job: ExtractionJob | None = None,
) -> ConnectorOut:
    synced_pages_count = getattr(credential, "_synced_pages_count", None)
    changed_pages_count = getattr(credential, "_changed_pages_count", None)

    if synced_pages_count is None or changed_pages_count is None:
        from django.db.models import F

        synced_pages_count = SyncedPage.objects.filter(credential=credential).count()
        changed_pages_count = (
            SyncedPage.objects.filter(credential=credential)
            .exclude(extraction_checksum=F("checksum"))
            .count()
        )

    if last_sync_job is None:
        last_sync_job = (
            SyncJob.objects.filter(credential=credential).order_by("-created_at").first()
        )
    if last_extraction_job is None:
        last_extraction_job = (
            ExtractionJob.objects.filter(credential=credential).order_by("-created_at").first()
        )

    return ConnectorOut(
        id=str(credential.id),
        provider=credential.provider,
        site_url=credential.site_url,
        status=credential.status,
        connected_by_email=credential.connected_by.email if credential.connected_by else None,
        last_sync_job=SyncJobBriefOut(
            status=last_sync_job.status,
            pages_updated=last_sync_job.pages_updated,
            finished_at=(
                last_sync_job.finished_at.isoformat() if last_sync_job.finished_at else None
            ),
        )
        if last_sync_job
        else None,
        last_extraction_job=_build_extraction_job_brief_out(last_extraction_job),
        synced_pages_count=synced_pages_count,
        changed_pages_count=changed_pages_count,
        created_at=credential.created_at.isoformat(),
    )


def _build_extraction_job_brief_out(job: ExtractionJob | None) -> ExtractionJobBriefOut | None:
    if not job:
        return None
    return ExtractionJobBriefOut(
        id=str(job.id),
        status=job.status,
        pages_scored=job.pages_scored,
        pages_extracted=job.pages_extracted,
        candidates_created=job.candidates_created,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


def _build_extraction_job_out(job: ExtractionJob) -> ExtractionJobOut:
    return ExtractionJobOut(
        id=str(job.id),
        status=job.status,
        pages_scored=job.pages_scored,
        pages_extracted=job.pages_extracted,
        candidates_created=job.candidates_created,
        error_message=job.error_message,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        created_at=job.created_at.isoformat(),
    )


def _build_candidate_out(candidate: CaptureCandidate, *, include_sources: bool) -> CandidateOut:
    promoted_slug = None
    if candidate.promoted_process_id:
        from apps.processes.models import Process

        try:
            promoted_slug = Process.objects.values_list("slug", flat=True).get(
                id=candidate.promoted_process_id
            )
        except Process.DoesNotExist:
            pass

    sources = None
    if include_sources:
        sources = [
            CandidateSourceBriefOut(
                id=str(s.id),
                page_title=s.synced_page.title,
                page_external_url=s.synced_page.external_url,
            )
            for s in CandidateSource.objects.filter(candidate=candidate).select_related(
                "synced_page"
            )
        ]

    return CandidateOut(
        id=str(candidate.id),
        title=candidate.title,
        slug=candidate.slug,
        description=candidate.description,
        probability_score=candidate.probability_score,
        automation_tier=candidate.automation_tier,
        automation_reasoning=candidate.automation_reasoning,
        integration_needs=candidate.integration_needs,
        status=candidate.status,
        promoted_process_slug=promoted_slug,
        sources=sources,
        created_at=candidate.created_at.isoformat(),
    )


def _build_page_out(page: SyncedPage) -> SyncedPageOut:
    return SyncedPageOut(
        id=str(page.id),
        external_id=page.external_id,
        external_url=page.external_url,
        space_key=page.space_key,
        title=page.title,
        content_md=page.content_md,
        last_synced_at=page.last_synced_at.isoformat(),
    )


def _extract_cloud_id(payload: dict) -> str:
    """Extract cloudId from Confluence webhook payload."""
    base_url = payload.get("baseUrl", "")
    if not base_url:
        return ""
    try:
        credential = ConnectorCredential.objects.filter(
            site_url=base_url.rstrip("/"),
            provider=ProviderChoices.CONFLUENCE,
            status__in=[CredentialStatus.ACTIVE, CredentialStatus.EXPIRED],
        ).first()
        return credential.cloud_id if credential else ""
    except Exception:
        logger.warning("Failed to extract cloud_id from webhook payload", exc_info=True)
        return ""
