# Schema Documenter

A small desktop app that connects to a database, lists its tables, and lets you
pick which ones to document. It produces a single **HTML page** or **PDF** with:

- an **entity relationship diagram** (crow's-foot notation) of the selected tables
- how the tables relate (foreign key, referenced table, cardinality)
- every column with its **data type**, nullability, default and key flags
- **primary keys**, **foreign keys** (with on delete / on update rules), **indexes** and unique constraints

## Download

**[Download the latest version](../../releases/latest)**. Pick the file for your computer:

| Your computer | File | How to open |
|---|---|---|
| Windows | `SchemaDocumenter-windows.zip` | Unzip, then double-click `SchemaDocumenter.exe` |
| Mac | `SchemaDocumenter-macos.zip` | Unzip, then right-click `SchemaDocumenter.app` and choose *Open* |
| Linux | `SchemaDocumenter-linux.tar.gz` | Extract, then run `./SchemaDocumenter` |

Nothing else needs to be installed. The first time you open it, Windows may say
"Windows protected your PC"; click *More info*, then *Run anyway*.

![App window](docs/screenshot.png)

Example output generated from the bundled sample database:
[`docs/examples/shop.html`](docs/examples/shop.html) · [`docs/examples/shop.pdf`](docs/examples/shop.pdf)

![ERD example](docs/erd.png)

## Supported databases

| Database | Driver (bundled) |
|---|---|
| PostgreSQL | psycopg 3 |
| MySQL / MariaDB | PyMySQL |
| SQL Server | pymssql |
| SQLite | built in |
| Anything else SQLAlchemy supports | choose **Custom SQLAlchemy URL** and install its driver when running from source |

The app only reads metadata (the system catalog). It never reads or changes table data,
so a read-only account is enough.

## Using the app

1. **Connect** – pick the database type and fill in host, port, database and credentials
   (or browse to a SQLite file).
2. **Choose tables** – every table in the database is listed. Tick the ones to document,
   or use *Select all*. Use *Search* to filter long lists. PostgreSQL and SQL Server
   show a *Schema* picker when there's more than one schema.
3. **Output** – set a title, choose *HTML page* or *PDF document*, and click
   *Generate document*. The file opens when it's ready.

Relationships are drawn between the tables you selected. A foreign key that points at a
table you didn't select is still listed in that table's details, marked *not documented*.

### Connecting to a Railway database

Use the host and port from `DATABASE_PUBLIC_URL` in your Postgres service's Variables,
or open a private tunnel with the Railway CLI and keep that window open while you work:

```bash
railway connect postgres --tunnel-only -P 5433
```

Then connect to host `127.0.0.1`, port `5433`, with the credentials the tunnel prints.

## Getting the executable

Executables have to be built on the operating system they'll run on (a Windows `.exe`
is built on Windows, and so on). There are two ways:

**Option A – let GitHub build all three.** On the repo page, go to *Releases → Draft a
new release*, create a tag such as `v1.0.0`, and publish. The *Build executables*
workflow tests the code and attaches `SchemaDocumenter-windows.zip`,
`SchemaDocumenter-macos.zip` and `SchemaDocumenter-linux.tar.gz` to the release, so
users download and double-click; no Python needed. You can also start the workflow
from the Actions tab, or push a tag from the command line:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

**Option B – build on your own machine** (needs Python 3.10+). On Windows, double-click
`build.bat`. On any system, the same steps by hand:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev]"
pyinstaller schemadoc.spec --noconfirm
```

The result is `dist\SchemaDocumenter.exe` on Windows, `dist/SchemaDocumenter.app` on
macOS and `dist/SchemaDocumenter` on Linux.

The executable is unsigned. Windows SmartScreen may show "Windows protected your PC";
choose *More info → Run anyway*. On macOS, right-click the app and choose *Open* the
first time. To avoid these prompts, sign the build with your own certificate.

## Running from source

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -e .
schema-documenter                # opens the window
```

On Linux you may need Tk first (`sudo apt install python3-tk`). To try it without a
database server, run `python scripts/make_sample_db.py` to create `sample.db`, a small
shop schema.

## Command line

After `pip install -e .` (see above), the `schemadoc` command documents tables without
opening the window:

```bash
schemadoc --url sqlite:///sample.db --list
schemadoc --url sqlite:///sample.db --tables customers,orders,order_items -o shop.html
schemadoc --url "postgresql://me:secret@db.local/app" --schema billing --all -o billing.pdf
```

`--format` defaults to the output file's extension.

## Project layout

```
pyproject.toml           dependencies (the only place they're listed)
build.bat                one-click Windows build
launcher.py              entry script used for the executable
schemadoc.spec           PyInstaller build recipe
src/schemadoc/
  gui.py                 Tkinter window
  cli.py                 command line
  connection.py          database types and connection URLs
  introspect.py          reads tables, columns, keys, indexes via SQLAlchemy (batched)
  models.py              plain data classes shared by everything else
  erd.py                 diagram layout and painting (no Graphviz needed)
  canvas.py              SVG and PDF drawing backends for the diagram
  render_html.py         self-contained HTML report
  render_pdf.py          PDF report (ReportLab)
  report.py              decides what the report says (shared by HTML and PDF)
  generate.py            ties reading and rendering together
scripts/make_sample_db.py
tests/                   pytest suite against the SQLite sample
.github/workflows/build.yml
```

## Notes

- The diagram layout is built in, so no Graphviz or other system tools are required.
  Tables are placed on a grid with related tables kept near each other, and lines are
  routed through the gaps so they don't cross over tables.
- In the PDF, every page is the same size. The diagram is arranged to suit a portrait page;
  when it's too big to read on one page, it keeps a readable size and continues onto more
  pages, split between rows of tables so no table is cut in half. In the HTML page you can
  zoom and download the diagram as SVG.
- Tables with more than 30 columns show their key columns first in the diagram, followed by
  "+ N more columns". Every column is still listed in the table details.
- The HTML report is a single file with no external requests, so it can be emailed or
  committed next to your code.
- Connections give up after 10 seconds if the server doesn't answer, with a message
  explaining what to check.

## Development

```bash
pip install -e ".[dev]"
pytest
```

MIT licensed.
