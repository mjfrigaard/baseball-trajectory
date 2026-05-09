# Deployment

The app is a standard Shiny for Python application — it can run
anywhere Shiny apps run. This page covers the supported targets.

## Local

For development:

```bash
pip install -e ".[dev]"
```

Then either the console script:

```bash
baseball-trajectory
```

Or the entry-point file directly:

```bash
shiny run app.py
```

Both bind to `127.0.0.1:8000`.

## Posit Connect Cloud

Two files at the repo root make the project deployable to
[Posit Connect Cloud](https://connect.posit.cloud/) out of the box:

| File                | Role                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------ |
| `requirements.txt`  | Connect Cloud's installer reads only this file. It does not run `pip install -e .` against `pyproject.toml`. |
| `app.py` (root)     | Deployment shim. Adds `src/` to `sys.path` and re-exports the Shiny `app` so Connect Cloud's primary-file mechanism finds it. |

### Steps

1. Push the project to a GitHub repository (Connect Cloud deploys from
   GitHub).
2. In Connect Cloud, click **New Content → Shiny for Python**.
3. Select your GitHub repository and branch.
4. Set **Primary file** to `app.py` — the root one, not
   `src/baseball_trajectory/app.py`.
5. Click **Deploy**.

Connect Cloud installs `requirements.txt`, imports the primary file,
and serves the resulting Shiny `App` object.

### Pinning dependencies

The default `requirements.txt` lists deps without version constraints
— Connect Cloud picks compatible versions at deploy time. For
reproducible deploys, pin to your working environment:

```bash
pip freeze | grep -E "^(shiny|polars|numpy|statsmodels|matplotlib|requests)==" > requirements.txt
```

Or use `pip-compile` (from `pip-tools`) to derive `requirements.txt`
from `pyproject.toml`:

```bash
pip install pip-tools
```

```bash
pip-compile pyproject.toml -o requirements.txt
```

Re-run on dependency changes and commit the result.

### Egress

The app fetches roster and career data from `https://statsapi.mlb.com`.
If your Connect Cloud account has egress restrictions, allowlist that
host.

### Why two `app.py` files?

The package layout uses `src/baseball_trajectory/app.py` for the real
Shiny code. The root-level `app.py` is a deployment shim — it exists
because Connect Cloud doesn't install the package, just runs the
primary file. Local development uses the console script
(`baseball-trajectory`), which goes through `__main__.py` and never
touches the root shim.

| File                                | Role                                                            |
| ----------------------------------- | --------------------------------------------------------------- |
| `src/baseball_trajectory/app.py`    | Real Shiny UI + server code.                                    |
| `app.py` (root)                     | Adds `src/` to `sys.path` and re-exports `app`. Used by Connect Cloud and `shiny run app.py`. |

## Other Shiny hosts

Posit Connect (on-prem), ShinyApps.io, and self-hosted Uvicorn all
support the same primary-file pattern. The root `app.py` is portable
across them.

For pure local serving without the console script:

```bash
shiny run app.py
```

For container deploys, install `requirements.txt` and run
`shiny run app.py` as the container entry point. A minimal Dockerfile:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY app.py .
EXPOSE 8000
CMD ["shiny", "run", "--host", "0.0.0.0", "--port", "8000", "app.py"]
```

## Documentation site

The docs themselves deploy to GitHub Pages — covered in the
**Publishing** section of the README.
