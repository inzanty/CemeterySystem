from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import CorrectionRequest, Grave


def is_moderator(user):
    return user.is_authenticated and user.is_active and (
        user.is_superuser or user.groups.filter(name="Moderators").exists()
    )


class ReviewConflict(ValidationError):
    def __init__(self, message, existing_grave=None):
        super().__init__(message)
        self.existing_grave = existing_grave


def review_request(pk, reviewer, decision, response):
    if not is_moderator(reviewer):
        raise PermissionDenied
    response = response.strip()
    if decision not in (CorrectionRequest.Status.APPROVED, CorrectionRequest.Status.REJECTED):
        raise ValidationError("Wybierz prawidłową decyzję.")
    if not response or len(response) > 4000:
        raise ValidationError("Podaj odpowiedź (maksymalnie 4000 znaków).")
    return _review_pending_request(pk, reviewer, decision, response)


@transaction.atomic
def _review_pending_request(pk, reviewer, decision, response):
    now = timezone.now()
    # The conditional write acquires the row's write lock before reading it.
    # This also serializes reviews on SQLite, where select_for_update is a no-op.
    claimed = CorrectionRequest.objects.filter(pk=pk, status=CorrectionRequest.Status.PENDING).update(
        reviewed_by=reviewer, reviewed_at=now, updated_at=now,
    )
    if not claimed:
        raise ReviewConflict("To zgłoszenie zostało już rozpatrzone. Decyzja jest ostateczna.")
    submission = CorrectionRequest.objects.get(pk=pk)
    result = None
    if submission.is_missing_grave and decision == CorrectionRequest.Status.APPROVED:
        location = dict(section_id=submission.proposed_section_id,
                        row=submission.proposed_row, number=submission.proposed_number)
        existing = Grave.objects.filter(**location).first()
        if existing:
            raise ReviewConflict("Grób o tej lokalizacji już istnieje. Zgłoszenie pozostaje oczekujące.", existing)
        try:
            with transaction.atomic():
                result = Grave.objects.create(**location)
        except IntegrityError:
            existing = Grave.objects.filter(**location).first()
            if existing is None:
                raise
            raise ReviewConflict("Grób o tej lokalizacji już istnieje. Zgłoszenie pozostaje oczekujące.", existing)
    CorrectionRequest.objects.filter(pk=pk).update(
        status=decision, admin_response=response, resulting_grave=result,
    )
    return CorrectionRequest.objects.get(pk=pk)
