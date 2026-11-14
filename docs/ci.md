# Continuous integration and merge protection

GitHub Actions runs `.github/workflows/ci.yml` for every pull request (including drafts),
push to `main`, merge queue entry, and manual dispatch. There are no path filters.
The Ubuntu 24.04 jobs run on full GitHub-hosted VMs with Docker, so cloud agents
without a local daemon can validate container behavior remotely.

## Required checks

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

## Enable merge enforcement (repository owner action)

A workflow file does not by itself prevent merging. After a successful run has
registered **CI required**, configure a branch ruleset in GitHub Settings → Rules →
Rulesets for `main`:

1. Set enforcement to **Active**, target `main`, and leave the bypass list empty.
2. Require a pull request before merging. No review-count requirement is needed
   solely to enforce CI; choose any review policy separately.
3. Require status check **CI required**, with GitHub Actions as the expected source.
4. Require branches to be up to date before merging (strict status checks).
5. Block force pushes and branch deletions.

For classic branch protection, select the same check, require up-to-date branches
and pull requests, and enable **Do not allow bypassing the above settings** to
include administrators. Preserve any existing stricter settings.

Repository administration permission is needed. The connected coding integration
may be able to publish workflows while lacking permission to manage protection.
No protection is enabled by this PR itself. Repository owners who can edit the rule
can still intentionally change it; CI is not a substitute for access control.

Verify enforcement with a PR whose CI fails: merging should be blocked. Also verify
that a PR with a missing or pending aggregate check cannot merge. Do not merge a
failing PR as a test.

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

Review and merge the CI PR, enable required checks, then update existing PR branches
from `main` and inspect the runs for their exact latest commit. For early validation,
the CI branch can be merged into an existing PR branch without merging either PR to
`main`; the Actions run will then validate the combined changes. Keep that dependency
visible in the PR description until the CI PR is merged.
