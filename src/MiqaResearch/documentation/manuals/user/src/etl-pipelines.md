(heading-etl-pipelines)=
# ETL Pipelines

The **ETL Pipelines** tab of a research project loads data into the project automatically from
files that arrive in a storage bucket, for example a nightly export from a lab system. You
decide which bucket to watch and which script reads the files. From then on, every new file is
processed without anyone having to start it.

A few terms appear throughout this page:

ETL Script
: A small program, written in Python or R, that reads the incoming files and returns rows of
  data. Your project can have its own **custom** scripts. Scripts provided by the platform are
  called **native** scripts and are read-only.

Script Version
: A saved, unchangeable copy of a script. Uploading a changed script always creates a new
  version, and older versions stay exactly as they were.

ETL Datatype
: The kind of data a script produces, for example *measurement* or *visit occurrence*. It
  decides which columns each row must have and where in the database the rows are stored.

Pipeline Binding
: A connection between a **source bucket** (where files arrive) and one Script Version. It
  also names the **raw bucket** that processed files are moved to afterwards.

ETL Job
: One run of a script over one file, or one folder of files.

(heading-etl-pipelines-access)=
## Who can do what

| Role | What you can do on the ETL Pipelines tab |
|---|---|
| Admin | Everything below, plus archiving scripts and changing the project's settings under **Defaults**. |
| Data Manager | Create and edit custom scripts, upload new versions, create bindings, retry failed jobs. |
| PI, Investigator | See every section (scripts, bindings, jobs, logs) but change nothing. |
| Other roles | The tab is not available. |

The tab has four sections, listed in the sidebar on its left: **Bindings**, **Scripts**,
**Jobs** and **Defaults**.

(heading-etl-pipelines-scripts)=
## Creating a custom script

1. Open the **ETL Pipelines** tab and select **Scripts** in the sidebar.
2. Under **New script**, enter a **Name**, an optional **Description**, and choose the script's
   **Source** file.
   - The file must end in `.py` (Python) or `.R` (R). The ending decides which language
     environment the script runs in.
   - The file must not be larger than the project's size limit, 256 KB unless an Admin has
     changed it.
3. Click **Create script**. The script appears in the list as version 1.

To change the name or description, click **Edit** next to the script. To change the code
itself, use **Add version**, choose the new file and click **Upload version**. Bindings that
already use an older version continue to use it. A new binding can use the new version right
away. Switching an existing binding to it is currently done by the platform administrator.

An Admin can **Archive** a script that is no longer needed. An archived script can no longer be
edited or chosen for a new binding. Scripts are never deleted, so every past job can still be
traced to the exact code that ran.

:::{note}
A new script must be linked to a Datatype before it can load any data. The tab does not yet
provide a way to choose it, so ask your platform administrator to set the Datatype for a new
script. Until then, its jobs fail with a "contract violation" error.
:::

### What a script has to do

A script receives the incoming files and the binding's settings. It returns one row at a time,
with the columns required by its Datatype. Every row must identify the study participant it
belongs to, either by `person_source_value` or by `alias1`. The platform then checks each row
before anything is saved:

- If **any** row is invalid, refers to an unknown participant, or matches more than one
  participant, the whole job fails and **nothing** is saved.
- A script cannot reach the network, the database or any other system. It can only read its
  input files.
- Running the same file again updates rows that were loaded earlier; it does not create
  duplicates.

Scripts run with limited time and memory. By default a run is stopped after 10 minutes.

(heading-etl-pipelines-bindings)=
## Creating a Pipeline Binding

A binding tells the platform to watch a location and process what arrives there.

1. Open **Bindings** and expand **New binding**.
2. Fill in the form:
   - **Source bucket** and **Source prefix**: the bucket, and optionally the folder inside it,
     where new files arrive.
   - **Script & version**: the script to run and the exact version to use.
   - **Raw bucket** and **Raw prefix**: where processed files are moved after a successful
     job.
   - **Sandbox overrides** (optional): a lower time limit (seconds), memory limit (MB) or CPU
     limit (millicores) for this binding. These can only be lower than the platform limits,
     never higher.
3. Click **Create binding**.

Your project can only use buckets it has been granted. If the form says *"This project has not
been granted access to that source bucket/prefix"*, or if there is a notice that no buckets are
granted yet, ask your platform administrator to grant the bucket to the project. Each source
location can belong to only one binding.

:::{note}
A new binding processes **each file on its own**. A binding can also be set to wait for a whole
folder to finish arriving and then process the folder as one job. A binding can also pass
settings to its script. Both of these are currently set up by the platform administrator.
:::

(heading-etl-pipelines-lifecycle)=
## What happens when a file arrives

1. **Detection.** The platform checks every binding's source location about every 30 seconds
   and notices new files.
   - For a binding that processes each file on its own, a job is created for the file.
   - For a folder binding, the platform waits until no new file has arrived in that folder for
     a while (5 minutes by default), then creates one job for the whole folder.
2. **Queueing.** A binding runs only one job at a time. Other new files wait, and are picked up
   one after another as earlier jobs finish.
3. **Running.** The script runs in an isolated environment. The job's status changes from
   *Pending* to *Running*.
4. **Loading.** If the script succeeds and every row passes the checks, all rows are saved
   together and the job becomes *Succeeded*. Otherwise the job becomes *Failed* and nothing is
   saved.
5. **Moving the files.** After a successful job, the input files are moved from the source
   bucket to the raw bucket, into a folder named after the job. They are copied first, the
   copy is checked, and only then is the original deleted. If the original repeatedly cannot be
   deleted, Admins and Data Managers receive an email and the file is left where it is for
   manual handling.

Files belonging to a failed job are **not** moved. They stay in the source bucket.

(heading-etl-pipelines-jobs)=
## Following jobs and reading logs

Open **Jobs** to see every job in the project, newest first. Each row shows the binding, the
script and version that ran, the attempt number and the status:

| Status | Meaning |
|---|---|
| Pending | Queued, waiting to start. |
| Running | The script is running now. |
| Succeeded | All rows were saved and the input files are being moved to the raw bucket. |
| Failed | Nothing was saved. Open the job to see why. |
| Stuck | The job has been running well past its time limit. The platform fails it automatically and, if the cause was a platform problem, starts it again. |

The list does not refresh by itself. Select **Jobs** again to see the latest status.

Click a job to open its details:

- the **Inputs**: each file's name, size and SHA-256 checksum;
- the **Log**: everything the script printed, followed by any error message from the platform.

Logs are kept for 30 days by default and then removed. The job itself is kept.

When reading a failed job's log:

- **A Python or R error**: the script itself failed. Fix the script and upload a new version.
  See the note under [Retrying a failed job](#heading-etl-pipelines-retry) for how to put the
  new version to use.
- **"Failed validation"** or a **contract violation**: the script returned a row with missing or
  wrong columns, or the script is not set up correctly.
- **"No Study Participant … matches"** or **"matches more than one"**: a participant reference
  in the data does not match exactly one participant in this project.
- **Timed out or killed**: the script ran longer than its time limit or ran out of memory.

If the platform itself was briefly unavailable, it retries the job automatically, up to three
attempts in total. These retries appear as new rows with a higher **Attempt** number.

(heading-etl-pipelines-retry)=
## Retrying a failed job

Admins and Data Managers see a **Retry** button on a failed job's detail page. Clicking it
creates a new job that:

- processes the **same input files**;
- uses the **same script version** as the failed job, even if the binding has since been
  changed to a newer version.

A retry is refused while the binding already has a job pending or running. Wait for that job to
finish, then try again. Every retry is recorded in the project's audit log.

:::{note}
Retry fixes problems in the data or on the platform side. If the script itself was wrong,
retrying runs the same faulty version again. Upload a corrected version first. A binding cannot
yet be edited on the tab, so ask your platform administrator to switch the binding to the new
version. New files are then processed with it.
:::

(heading-etl-pipelines-defaults)=
## Defaults (Admins)

The **Defaults** section lists the native scripts the platform provides. It also lets an Admin
override two settings for this project:

- **Log retention days**: how long job logs are kept.
- **Max script source bytes**: the largest script file that may be uploaded.

Leave a field empty to use the platform default. PIs, Investigators and Data Managers can see
this section but cannot change it.
