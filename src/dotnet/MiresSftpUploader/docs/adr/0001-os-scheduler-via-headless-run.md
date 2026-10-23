# Scheduling is the operating system's job, via a Headless Run

"Run as a scheduled task" is met by a run-once headless mode (same configuration, logging and exit codes as the UI) that Windows Task Scheduler, cron or launchd invokes, not by an in-app timer or resident service. An in-app scheduler would need a long-lived process, tray behaviour and missed-run handling on three operating systems, and scheduled runs must work on machines with no display. Overlapping Runs are prevented by a single-instance lock, so the OS scheduler and a person using the UI cannot race on the Upload State.
