from django.conf import settings
from django.db import models

class Profile(models.Model):
    """Per-user job-search config: their own criteria, not shared."""
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    yoe_min = models.PositiveSmallIntegerField(default=0)
    yoe_max = models.PositiveSmallIntegerField(default=99)
    target_locations = models.JSONField(default=list, blank=True)   # ["Pune", "Remote"]
    must_have_skills = models.JSONField(default=list, blank=True)
    red_flag_terms = models.JSONField(default=list, blank=True)     # agency keywords to filter out
    master_resume = models.JSONField(default=dict, blank=True)      # structured resume data

    def __str__(self):
        return f"Profile({self.owner})"


class JobStage(models.TextChoices):
    NEW = "new", "New"
    FILTERED_OUT = "filtered_out", "Filtered out"
    NEEDS_REVIEW = "needs_review", "Needs review"
    SKIPPED = "skipped", "Skipped"
    TAILORING = "tailoring", "Tailoring"
    READY = "ready", "Ready"
    APPLIED = "applied", "Applied"
    EXPIRED = "expired", "Expired"


class Job(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs")
    source = models.CharField(max_length=20)          # linkedin/indeed/naukri/hirist/instahyre/ats
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=1000)
    yoe_min = models.PositiveSmallIntegerField(null=True, blank=True)
    yoe_max = models.PositiveSmallIntegerField(null=True, blank=True)
    fingerprint = models.CharField(max_length=64)      # dedupe key
    stage = models.CharField(max_length=20, choices=JobStage.choices, default=JobStage.NEW)
    score = models.FloatField(null=True, blank=True)
    reasons = models.JSONField(default=list, blank=True)
    apply_method = models.CharField(max_length=10, blank=True)   # auto | manual
    raw = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "fingerprint"], name="unique_job_per_owner")
        ]

    def __str__(self):
        return f"{self.title} @ {self.company}"


class AppStatus(models.TextChoices):
    APPLIED = "applied", "Applied"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    ASSESSMENT = "assessment", "Assessment"
    INTERVIEW = "interview", "Interview"
    OFFER = "offer", "Offer"
    NOT_SELECTED = "not_selected", "Not selected"
    NO_RESPONSE = "no_response", "No response"
    WITHDRAWN = "withdrawn", "Withdrawn"


class Application(models.Model):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="application")
    method = models.CharField(max_length=10)          # auto | manual
    status = models.CharField(max_length=20, choices=AppStatus.choices, default=AppStatus.APPLIED)
    reason = models.CharField(max_length=40, blank=True)
    reason_source = models.CharField(max_length=10, blank=True)   # email | inferred | manual
    locked_by_user = models.BooleanField(default=False)
    applied_at = models.DateTimeField()

    def __str__(self):
        return f"Application({self.job})"


class ApplicationEvent(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20, choices=AppStatus.choices)
    source = models.CharField(max_length=10)          # system | email | manual
    confidence = models.FloatField(null=True, blank=True)
    email_message_id = models.CharField(max_length=255, blank=True, null=True, unique=True)
    note = models.TextField(blank=True)
    occurred_at = models.DateTimeField()

    class Meta:
        ordering = ["occurred_at"]

    def __str__(self):
        return f"{self.application} -> {self.status}"