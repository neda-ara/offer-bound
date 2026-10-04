import email
import imaplib
import re
from email.header import decode_header

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone

from tracker.models import Job, JobStage

SEPARATOR_RE = re.compile(r'\n-{5,}\n')
BADGE_RE = re.compile(r'^(Apply with resume & profile|Easy Apply|\d+ connections?|Actively recruiting)$', re.IGNORECASE)
HEADER_RE = re.compile(r'^(Your job alert for|New jobs (in|match))', re.IGNORECASE)
VIEW_JOB_RE = re.compile(r'^View job:\s*(\S+)', re.IGNORECASE)
SEE_ALL_RE = re.compile(r'^See all jobs', re.IGNORECASE)


def parse_linkedin_digest(text: str) -> list[dict]:
    """Splits a LinkedIn job-alert digest's plain-text body into job entries."""
    blocks = SEPARATOR_RE.split(text)
    jobs = []
    for block in blocks:
        lines = [l.strip() for l in block.splitlines()]
        lines = [l for l in lines if l]
        if not lines or any(SEE_ALL_RE.match(l) for l in lines):
            continue  # empty block or the "See all jobs" footer

        url = None
        content_lines = []
        for l in lines:
            m = VIEW_JOB_RE.match(l)
            if m:
                url = m.group(1)
                continue
            if HEADER_RE.match(l) or BADGE_RE.match(l):
                continue
            content_lines.append(l)

        if not url or len(content_lines) < 2:
            continue  # not a real job block

        title = content_lines[0]
        company = content_lines[1]
        location = content_lines[2] if len(content_lines) > 2 else ""

        # Strip LinkedIn's tracking query params, keep the canonical job URL
        job_id_match = re.search(r'/jobs/view/(\d+)', url)
        clean_url = (
            f"https://www.linkedin.com/jobs/view/{job_id_match.group(1)}/"
            if job_id_match else url.split('?')[0]
        )

        jobs.append({"title": title, "company": company, "location": location, "url": clean_url})
    return jobs


def get_plain_text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
        return ""
    charset = msg.get_content_charset() or "utf-8"
    return msg.get_payload(decode=True).decode(charset, errors="replace")


class Command(BaseCommand):
    help = "Fetch LinkedIn job alert emails via IMAP and create Job rows."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Username of the Job owner")
        parser.add_argument("--label", default="JobAlerts/LinkedIn", help="Gmail label/folder to scan")
        parser.add_argument("--dry-run", action="store_true", help="Parse and print, don't write to DB")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            owner = User.objects.get(username=options["owner"])
        except User.DoesNotExist:
            raise CommandError(f"No user named '{options['owner']}'")

        gmail_user = settings.GMAIL_USER
        gmail_pass = settings.GMAIL_APP_PASSWORD
        if not gmail_user or not gmail_pass:
            raise CommandError("Set GMAIL_USER and GMAIL_APP_PASSWORD in .env")

        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(gmail_user, gmail_pass)
        status, _ = imap.select(f'"{options["label"]}"')
        if status != "OK":
            raise CommandError(f"Could not open label '{options['label']}' — check it exists in Gmail")

        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            raise CommandError("IMAP search failed")

        msg_nums = data[0].split()
        self.stdout.write(f"Found {len(msg_nums)} unread message(s) in {options['label']}")

        created, dupes, skipped = 0, 0, 0

        for num in msg_nums:
            status, msg_data = imap.fetch(num, "(RFC822)")
            if status != "OK":
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            subject_raw, encoding = decode_header(msg.get("Subject", ""))[0]
            subject = subject_raw.decode(encoding or "utf-8") if isinstance(subject_raw, bytes) else subject_raw

            body = get_plain_text_body(msg)
            parsed_jobs = parse_linkedin_digest(body)

            if not parsed_jobs:
                self.stdout.write(self.style.WARNING(f"  No jobs parsed from: {subject}"))
                skipped += 1
                continue

            for job_data in parsed_jobs:
                if options["dry_run"]:
                    self.stdout.write(f"  [dry-run] {job_data['title']} @ {job_data['company']} ({job_data['location']})")
                    continue
                try:
                    Job.objects.create(
                        owner=owner,
                        source="linkedin",
                        title=job_data["title"],
                        company=job_data["company"],
                        location=job_data["location"],
                        url=job_data["url"],
                        stage=JobStage.NEW,
                        raw={"email_subject": subject, "fetched_at": timezone.now().isoformat()},
                    )
                    created += 1
                except IntegrityError:
                    dupes += 1

            if not options["dry_run"]:
                imap.store(num, "+FLAGS", "\\Seen")

        imap.close()
        imap.logout()

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created}, Duplicates skipped: {dupes}, Unparseable emails: {skipped}"
        ))