# Continuous integration

GitHub Actions runs `.github/workflows/ci.yml` for every pull request (including drafts),
push to `main`, merge queue entry, and manual dispatch. There are no path filters.
The Ubuntu 24.04 jobs run on full GitHub-hosted VMs with Docker, so cloud agents
without a local daemon can validate container behavior remotely.

## CI checks

- **Backend quality**: code size limits, Ruff, strict mypy, all backend tests and
  at least 95% coverage. `RUN_DOCKER_TESTS=1` enables real Docker tests such as the
  deployment bind-mount regression from PR #4. `docker info` must succeed first.
- **Frontend quality**: clean `npm ci`, ESLint with zero warnings, all Vitest tests
  with the configured coverage thresholds, TypeScript and production Vite build.
- **Docker integration**: builds both production images, runs PostgreSQL and real
  Alembic migrations, starts the application, verifies health and config reload,
  and checks the built frontend serves HTML. This uses only disposable CI data.
- **CI required**: a stable aggregate check. It runs after all jobs, including on
  failure, and succeeds only when every job succeeded. Skips and cancellations
  are failures, not green results.

Actions are pinned to commit SHAs. The workflow has read-only repository permissions,
does not use deployment secrets, and runs PR code on ephemeral hosted runners.
It uses `pull_request`, never privileged `pull_request_target` execution.
Python 3.12 and Node 22 match the production Dockerfiles. Backend dependencies retain
the project's declared version ranges; frontend installs use the committed lockfile.

## Merge policy

Branch protection is outside the current scope at the owner's request. CI reports
results through **CI required**; it does not block GitHub's merge operation by itself.
The check name is unchanged so existing links and workflow consumers remain stable.

Before merging, wait for automated review, resolve findings, obtain an independent
review, and confirm checks pass for the latest PR head. After merging, inspect the
run on `main` and verify fully resolved linked issues closed. Use a supported closing
reference in the PR description for completed issues; keep partial work explicit.

## Local commands and rollout

```bash
python -m pip install -e './backend[dev]'
(cd frontend && npm ci)
make quality-check
make frontend-build
# Requires a running Docker daemon; enables the bind-mount regression when present.
RUN_DOCKER_TESTS=1 make coverage
bash scripts/test_docker_ci.sh
```

The CI container script uses a unique Compose project and removes only that project's
containers and volumes on exit. It never invokes the production deployment script.

The CI workflow and deployment bind-mount regression are merged into `main`.
Update PR branches from `main` when needed and inspect the runs for their exact
latest commit before merging. Publishing or merging a PR does not deploy it.
