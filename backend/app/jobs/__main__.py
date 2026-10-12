"""Run a scheduled job:  python -m app.jobs <job-name>

Example crontab (server in Asia/Dhaka time):
  15 0 * * *    cd /srv/smp/backend && .venv/bin/python -m app.jobs daily-cost
  30 0 * * *    cd /srv/smp/backend && .venv/bin/python -m app.jobs expected-charges
  45 0 * * *    cd /srv/smp/backend && .venv/bin/python -m app.jobs expire-assignments
  0 9 * * *     cd /srv/smp/backend && .venv/bin/python -m app.jobs renewal-reminders
  */15 * * * *  cd /srv/smp/backend && .venv/bin/python -m app.jobs appointment-reminders
  0 10 * * *    cd /srv/smp/backend && .venv/bin/python -m app.jobs escalations
  0 18 * * *    cd /srv/smp/backend && .venv/bin/python -m app.jobs dmd-digest
"""

import sys

from app.core.clock import today
from app.db.session import SessionLocal
from app.jobs.tasks import JOBS


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in JOBS:
        print(f"usage: python -m app.jobs <{'|'.join(JOBS)}>")
        return 2
    with SessionLocal() as db:
        result = JOBS[argv[1]](db, today())
    print(f"{argv[1]}: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
