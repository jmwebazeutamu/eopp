# Economic Opportunities Pathway Platform (EOPP)

Case management and referral engine for the World Bank Ethiopia youth employment
pilot. Django + DRF backend, React web client, Flutter field app.

Specification: [`docs/YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md`](docs/YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md)

## Quick start

Requires Docker and Docker Compose. On a Mac or Windows host, develop inside a
Multipass VM (spec §2.1):

```bash
multipass launch --name yep-dev --cpus 4 --memory 8G --disk 40G \
  --cloud-init infra/multipass/cloud-init.yaml 22.04
multipass mount . yep-dev:/home/ubuntu/youth-employment-platform
multipass shell yep-dev
```

Then, from the repository root:

```bash
./scripts/bootstrap.sh
```

That generates `infra/.env`, builds the images, starts the stack, and applies
migrations. Create your first administrator:

```bash
cd infra
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  exec web python manage.py createsuperuser
```

| Service | URL |
|---|---|
| API and admin | http://localhost:8007/admin/ |
| API docs (Swagger) | http://localhost:8007/api/docs/ |
| OpenAPI schema | http://localhost:8007/api/schema/ |
| Health check | http://localhost:8007/healthz/ |
| MinIO console | http://localhost:8008/ |
| Web app (Vite) | http://localhost:8100/ |

The React app runs on the host rather than in a container:

```bash
cd web && npm install && npm run dev
```

## Repository layout

```
backend/    Django + DRF — the API and domain logic
web/        React + TypeScript + Ant Design (Sprint 3+)
mobile/     Flutter offline field app (Sprints 8-9)
infra/      Docker Compose, Traefik, Multipass provisioning
docs/       Specification
scripts/    Bootstrap and operational scripts
```

## Development

See [`CLAUDE.md`](CLAUDE.md) for commands, conventions, and current sprint status.

## Status

**Sprint 0** — environment, Django skeleton, user and role model with the ten
roles from spec §7, RBAC scaffolding, JWT authentication, CI.

**Sprint 1** — Youth (§4.1) with consent capture, Case (§4.2) with caseload and
woreda scoping, Ethiopian location reference data, Django admin, and the case
manager's case list and detail screens.

**Sprint 2** — Profiling and Eligibility (§4.3), Pathway Assignment with revision
history (§4.4), Partner organisations (§4.11), and partner-institution scoping.

**Sprint 3** — the referral engine: the Referral entity (§4.6), the taxonomy as
admin-editable configuration (§5), the state machine (§6.2), the two-referral
parallel cap (§6.3), and the referral stack (§6.4).

**Sprint 4** — the Alert entity (§4.13), scheduled detection of stalled cases,
overdue partner confirmations, and the §6.2 onward/replacement prompts, with
auto-resolution when the underlying condition clears.

Sprint 5 next: training enrolment and placement with retention checkpoints.
