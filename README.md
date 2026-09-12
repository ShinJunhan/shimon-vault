# ShimonVault

**Event-Driven Security Detection and Automated Response for a Hybrid Cloud Platform**

[![CI](https://github.com/ShinJunhan/shimon-vault/actions/workflows/ci.yml/badge.svg)](https://github.com/ShinJunhan/shimon-vault/actions/workflows/ci.yml)
[![CD](https://github.com/ShinJunhan/shimon-vault/actions/workflows/cd.yml/badge.svg)](https://github.com/ShinJunhan/shimon-vault/actions/workflows/cd.yml)

## 🗨️ Project Introduction

ShimonVault is a secure internal operations platform deployed on AWS. Teams upload documents, schedule meetings, and every action taken on the platform is logged, monitored and defended while the service is running.

This is an individual project, built alone against the same brief as the Lock & Lock team project. The purpose was to find out which parts of that platform I understood as an engineer and which parts I only understood as a reviewer. The rule I set was that the brief could be the same and the mechanism had to be different: detection lives in application middleware, response lives in Lambda, scheduling lives in EventBridge, and the audit trail lives in DynamoDB.

Nothing in this repository was copied from the team repository. Where the team answered a problem with a container on an EC2 instance, this build answers it with the AWS service that owns the problem.

## 💠 Project Type

- Individual project, built from an empty repository
- Same four-week brief as the Lock & Lock team project, deliberately different execution

## 💠 Scope & Ownership

Solo build. Every area below is mine.

| Area | What it covers | Directory |
|---|---|---|
| Infrastructure · IaC | VPC, subnets, ALB, EC2, RDS, S3, DynamoDB, Lambda, SNS, EventBridge, IAM | `terraform/` |
| Application · API | FastAPI, SQLAlchemy models, JWT auth, role-based access, audit middleware | `app/` |
| Frontend | React SPA baked into the application image at build time | `frontend/` |
| Serverless response | Five Lambda handlers for blocking, logging, file validation and meeting lifecycle | `lambda/` |
| Monitoring · Alerting | Prometheus, Grafana, Alertmanager and the Telegram relay on the on-premises host | `monitoring/` |
| Configuration management | Docker and CloudWatch agent roles, dynamic EC2 inventory, stack verification | `ansible/` |
| CI/CD | Lint, test and image build on every push; blue/green deploy on main | `.github/workflows/` |
| Operations · Demo | One-command deploy and teardown, replication setup, five attack simulations | `scripts/` |

## 💠 The Three Modules

| Module | What it does |
|---|---|
| **SecureDocs** | Upload, list, download, version and soft-delete documents. Bytes live in S3 under `{owner_id}/{date}/{uuid}-{filename}`, encrypted at rest, with versioning on the bucket. Downloads are presigned URLs that expire after 15 minutes. Every access attempt is logged. |
| **ShimonMeet** | Create, update, cancel and join meetings. Each meeting gets a random join token. Creating a meeting registers two one-time EventBridge rules: a reminder 10 minutes before the start, and an archive at the end time. |
| **AuditStream** | The live feed of everything the other two modules did. Every request is written to DynamoDB by middleware, read back by the admin console, and mirrored into PostgreSQL for reporting. |

---

## ShimonVault: Detection in the Application, Response in the Cloud

A hybrid platform (AWS ↔ on-premises) built on three ideas. Nothing gets to skip the audit trail, because the logger is middleware rather than a call each route has to remember. The thing that responds to a failure is not part of the failure, because the response path is Lambda behind SNS rather than a process on a machine that may itself be down. A defence nobody has attacked is a configuration, so all five attack scenarios are buttons inside the product that fire real requests at real endpoints.

## Architecture at a Glance

```
Internet
  │  Cloudflare DNS only, grey cloud (shimonvault.junhanshin.com)
  ▼
ALB  ── public subnets 10.0.1.0/24 (AZ a) · 10.0.4.0/24 (AZ c)
  │      alongside: Bastion (SSH from my IP only), NAT instance (t3.micro, iptables masquerade)
  │      health check: GET /health every 30s, 2 healthy / 2 unhealthy
  ▼
App EC2 (blue)   ── private subnets 10.0.2.0/24 (AZ a) · 10.0.3.0/24 (AZ c)
App EC2 (green)     Docker, uvicorn on :8000, node_exporter on :9100
  │
  ├─► RDS PostgreSQL 16 (db.t3.micro, private, logical replication enabled)
  ├─► S3   shimonvault-docs-<account>   ·   shimonvault-reports-<account>
  ├─► DynamoDB   audit-log · incidents · meetings
  ├─► SNS   security-alert · infra-alert · meeting-reminders
  └─► EventBridge   one-time at() rules, created per meeting

Tailscale mesh (100.64.0.0/10)
  ├─ proj-mgmt      Prometheus · Grafana · Alertmanager · cAdvisor · Portainer · Telegram relay
  └─ proj-ubuntu01  PostgreSQL read replica on :5433 · NFS share
```

Security groups reference each other rather than CIDR ranges. The app group accepts 8000 only from the ALB group and 22 only from the bastion group. The RDS group accepts 5432 only from the app group and the bastion group. Ports 9100 (node exporter), 2376 (Docker TLS) and 2049 (NFS) are open only to the Tailscale range.

---

## 🚀 Getting Started

### Prerequisites

- AWS CLI configured (`aws configure`)
- Terraform 1.7 or later
- Docker Desktop running
- An EC2 key pair in `ap-northeast-2`, and an SSH key at `~/.ssh/id_ed25519_shimonvault`
- Tailscale installed on the on-premises hosts, with an auth key from the admin console

### One-time state bootstrap

Terraform state lives on an S3 backend with a DynamoDB lock table. Both are created once by hand and are never managed by Terraform, so `terraform destroy` can never delete the state it is writing to.

```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws s3 mb s3://shimonvault-tfstate-$AWS_ACCOUNT_ID --region ap-northeast-2
aws s3api put-bucket-versioning \
  --bucket shimonvault-tfstate-$AWS_ACCOUNT_ID \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block \
  --bucket shimonvault-tfstate-$AWS_ACCOUNT_ID \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

aws dynamodb create-table \
  --table-name shimonvault-tfstate-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-2
```

Then put your account ID into the backend block in `terraform/main.tf`.

### Configure

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# fill in every CHANGEME value: your public IP /32, key pair name, DB password,
# JWT secret, Tailscale auth key, Docker Hub username, alert email,
# and the Tailscale IPs of proj-mgmt and proj-ubuntu01
```

`terraform.tfvars` is gitignored. Nothing sensitive is ever committed, and `app/.env` is generated from Terraform outputs rather than written by hand.

## Deployment

One command stands the whole environment up. It takes about 15 minutes, and RDS is the slow part.

```bash
bash scripts/deploy.sh
```

`deploy.sh` runs in order:

| Step | What happens |
|---|---|
| 0 | Detects your current public IP and rewrites `your_ip_cidr` in `terraform.tfvars`, so the bastion rule follows you between networks |
| 0.5 | Reads proj-mgmt's own Tailscale address for the Prometheus URL |
| 1 – 2 | `terraform init` and `terraform apply` |
| 3 | `generate_env.sh` writes `app/.env` from Terraform outputs: RDS endpoint, bucket names, table names, SNS ARNs |
| 4 | `update_ssh_config.sh` rewrites the bastion jump-host entry |
| 5.5 | Points the Cloudflare record for `shimonvault.junhanshin.com` at the current ALB, unproxied |
| 6 – 7 | Waits for bastion SSH, then polls the app until `/health` answers, up to 4 minutes |
| 8.5 | Seeds the three demo accounts, idempotently |
| 11 | Installs node_exporter on the EC2 instances through Ansible |
| 12 | `setup_replica.sh` configures logical replication from RDS to proj-ubuntu01 |
| 13 | `ansible-playbook playbooks/verify_stack.yml` checks the whole stack end to end |
| 14 | Fetches the Docker TLS certificates and repoints Portainer at the new instance |

### Monitoring stack (on-premises, always on)

The monitoring host is never destroyed with the AWS environment.

```bash
cp .env.example monitoring/.env
# fill in DB_PASSWORD, GRAFANA_PASSWORD, SLACK_WEBHOOK_URL,
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
cd monitoring && docker compose up -d
```

Seven containers come up: Prometheus (`:9090`), Grafana (`:3000`), Alertmanager (`:9093`), node exporter (`:9100`), cAdvisor (`:8080`), the Telegram relay (`:8001`) and Portainer (`:9000`).

### Lambda packaging

Terraform zips each Lambda directory at apply time through `archive_file`, so the normal path needs no manual step. `scripts/package_lambdas.sh` builds the same five zips with their dependencies and the shared `notification.py` helper, for when a handler needs a real package installed.

### Teardown (required after every session)

```bash
bash scripts/destroy.sh
```

`destroy.sh` removes the EC2 nodes from the Tailscale mesh first, runs `terraform destroy`, and then verifies rather than trusts. It re-checks EC2 instances, RDS, load balancers, the NAT instance, leftover EBS volumes, Lambda functions and stale Tailscale nodes, and prints the console links for the two manual checks that are worth a human eye.

State is preserved across sessions. The S3 bucket and the lock table are outside Terraform, so the next apply picks up where the last one left off.

---

## Directory Structure

```
shimon-vault/
├── README.md
├── app/                          FastAPI application (Docker image root)
│   ├── main.py                   lifespan, routers, SPA fallback, /health
│   ├── config.py                 every setting read from the environment
│   ├── database.py               lazy write and read engines, psycopg2 only
│   ├── models.py                 5 tables, UUID keys, 13 audit event types
│   ├── auth.py                   bcrypt, JWT, require_role() dependency
│   ├── rate_limit.py             the one shared slowapi limiter
│   ├── routers/                  6 routers, 26 endpoints
│   │   ├── auth_router.py        register, login, logout
│   │   ├── docs_router.py        upload, list, download, delete, versions
│   │   ├── meetings_router.py    create, list, get, update, cancel, join, archive
│   │   ├── audit_router.py       feed, incidents, my-activity
│   │   ├── admin_router.py       dashboard summary, timeseries, infra
│   │   └── demo_router.py        the five one-click attack simulations
│   ├── services/                 S3, DynamoDB audit, EventBridge, Prometheus, notify, rate limiter
│   ├── middleware/
│   │   └── audit_middleware.py   logs every request, counts, suspends, alerts
│   └── Dockerfile                3 stages: Vite build, pip build, slim runtime
├── frontend/                     React SPA, built into the image
│   └── src/                      Login, Docs, Meetings, Console, api.js, toast
├── terraform/                    27 files, 90 resource blocks
│   ├── main.tf                   provider, S3 backend, caller identity
│   ├── vpc.tf                    VPC, 4 subnets, IGW, route tables
│   ├── alb.tf                    ALB, blue and green target groups, 80 and 443
│   ├── acm.tf                    the cert the 443 listener serves, DNS-validated
│   ├── app_ec2_blue.tf           the live instance
│   ├── app_ec2_green.tf          created only when deploy_green = true
│   ├── asg.tf                    launch template, scale policies, CPU alarms
│   ├── rds.tf                    PostgreSQL 16, logical replication parameters
│   ├── s3.tf                     docs and reports, encrypted, versioned
│   ├── dynamodb.tf               audit-log, incidents, meetings
│   ├── lambda.tf                 5 functions, zipped at apply time
│   ├── sns.tf                    security-alert, infra-alert, meeting-reminders
│   ├── eventbridge.tf            the static warm-up rule
│   ├── iam.tf                    2 roles, one inline policy per Lambda
│   ├── security_groups.tf        5 groups, referencing each other
│   ├── nat_instance.tf           t3.micro with iptables masquerade
│   ├── bastion.tf                SSH from my IP only
│   ├── cloudwatch.tf             high CPU, instance status check, ALB 5xx
│   ├── backend.tf                the one-time state bootstrap, documented
│   └── templates/
│       └── app_user_data.sh.tpl  boot script: Tailscale, Docker, .env, container
├── lambda/                       5 handlers, python3.12
│   ├── block_ip/                 NACL deny rule, incident record, notify
│   ├── log_incident/             SNS message to the incidents table
│   ├── validate_file/            magic-byte check on S3 upload
│   ├── meeting_notify/           fires 10 minutes before a meeting
│   ├── meeting_expire/           fires at meeting end
│   └── shared/notification.py    the Slack and Telegram helper
├── monitoring/                   on-premises stack, docker compose
│   ├── prometheus/
│   │   ├── prometheus.yml        4 scrape jobs, 15s interval
│   │   ├── rules/                4 alert rules
│   │   └── targets/              file_sd JSON, rewritten by deploy.sh
│   ├── alertmanager/             Slack receiver plus a webhook to the relay
│   ├── grafana/dashboards/       infra_health.json, auditstream.json
│   └── telegram_relay/           the bridge Alertmanager posts to
├── ansible/
│   ├── inventory.aws_ec2.yml     dynamic inventory, grouped by the Role tag
│   ├── playbooks/                setup_app, setup_monitoring, verify_stack
│   └── roles/                    docker_app, monitoring_stack, cloudwatch_agent
├── scripts/
│   ├── deploy.sh                 apply to healthy in one command
│   ├── destroy.sh                teardown, then verify 9 resource types
│   ├── generate_env.sh           app/.env from Terraform outputs
│   ├── setup_replica.sh          RDS to on-premises logical replication
│   ├── fetch_docker_certs.sh     the Docker TLS certs Portainer connects with
│   ├── update_ssh_config.sh      rewrites ~/.ssh/config for the new bastion
│   ├── package_lambdas.sh        zips the five functions with dependencies
│   ├── generate_report.py        incident report from DynamoDB
│   └── simulate_*.sh|.py         the terminal versions of the five demos
├── db/                           schema.sql, seed.sql, schema_from_rds.sql
├── tests/                        pytest, SQLite in memory, no AWS needed
├── docs/                         the GitHub Pages landing page
└── .github/workflows/            ci.yml and cd.yml
```

---

## Security Controls

| Control | Where it lives | Trigger | Response |
|---|---|---|---|
| Request auditing | `middleware/audit_middleware.py` | Every request except `/health`, `/metrics`, `/favicon.ico` | One row in the DynamoDB audit log, with method, path, status, IP and severity |
| Role-based access | `auth.require_role()` | Any route declaring required roles | HTTP 403, logged as `doc_access_denied` |
| Account suspension | `audit_middleware` | 5 access-denied responses from one account | `users.suspended = true`, incident record, Slack and Telegram alert |
| Download rate limit | `rate_limit.py` and `docs_router` | 10 downloads in 60 seconds per IP | HTTP 429, logged as `rate_limit_hit` |
| Exfiltration report | `audit_middleware` | The first 429 on a `/docs/download` path from an IP | JSON incident report written to the reports bucket, incident record, one alert per IP per burst |
| Login failure tracking | `auth_router` | 5 failures from one IP, then 8 | Warning alert at 5, incident record and critical alert at 8 |
| Upload validation | `lambda/validate_file` | S3 `ObjectCreated:Put` on the docs bucket | Reads the first 512 bytes, rejects on signature or size, deletes the object, writes an incident |
| Automatic IP block | `lambda/block_ip` | An SNS message on the security-alert topic | Inserts a DENY entry into the network ACL at the lowest free rule number between 1 and 99 |
| Presigned downloads | `services/s3_service.py` | Every document download | A URL that expires in 900 seconds, so a leaked link is short-lived |
| Password hashing | `auth.py` | Registration and login | SHA-256 pre-hash, then bcrypt at work factor 12 |
| Least-privilege IAM | `terraform/iam.tf` | Every Lambda | One inline policy per function rather than one shared policy |

### Why the block is a network ACL and not a security group

A security group has allow rules only. There is no such thing as a security group deny rule, so an automatic block cannot be expressed there. Network ACLs are stateless and ordered by rule number, which is exactly what an automatic block needs. `block_ip` reads the existing entries, takes the lowest free number between 1 and 99, and inserts a DENY for `<ip>/32`. Rule numbers 100 and above are left for the ordinary allow rules.

## Detection to Response

```
request
  └─ AuditMiddleware (outermost layer, wraps every route)
       ├─ status 401 → login_failure    severity warning
       ├─ status 403 → doc_access_denied severity warning → count per account
       │                                   at 5: suspend + incident + notify
       ├─ status 429 → rate_limit_hit    severity warning
       │                on /docs/download: S3 report + incident + notify (once per IP)
       ├─ status 5xx → severity critical
       └─ every case  → DynamoDB audit-log row

incident record
  └─ DynamoDB incidents table
  └─ mirrored into the audit log as a critical `suspicious` event
  └─ Slack and Telegram through notify_all()

S3 upload
  └─ ObjectCreated:Put → validate_file Lambda → magic bytes → delete + incident on reject

SNS security-alert
  └─ block_ip Lambda      → NACL DENY entry
  └─ log_incident Lambda  → incidents table

SNS infra-alert
  └─ log_incident Lambda
  └─ email subscription
```

---

## Demo Scenarios

All five are admin-only endpoints under `/demo`, gated by `DEMO_ENABLED`. Each one logs in as a real seeded account and calls real endpoints over HTTP, so what appears in the audit feed is the application running rather than fixture data. Every scenario also has a terminal equivalent in `scripts/`, for when the app itself is the thing under test.

| Act | Endpoint | Script | What it proves |
|---|---|---|---|
| 1 | `POST /demo/test-notification` | | Slack and Telegram wiring is live |
| 2 | `POST /demo/credential-stuffing` | `simulate_credential_stuffing.sh` | 30 login attempts with weak passwords produce real 401s, the failure counter crosses both thresholds, and the alerts fire |
| 3 | `POST /demo/access-control` | `simulate_access_control.sh` | A viewer account repeatedly requests a document it does not own, gets real 403s, and is suspended on the fifth |
| 4 | `POST /demo/exfiltration` | `simulate_exfiltration.py` | An editor re-downloads a real document until the limiter trips, producing a 429, an S3 incident report and one alert |
| 5 | `POST /demo/ddos` | `simulate_ddos.sh` | A concurrent burst at `/docs/list` raises the real Prometheus request rate and CPU |

The attacker address is `203.0.113.42` by default, inside the RFC 5737 documentation range, sent as `X-Forwarded-For` so the audit trail shows a plausible source that belongs to nobody.

`DEMO_ENABLED=false` turns every one of these into a 403. A public "launch attack" button would itself be a vulnerability, which is why the master switch exists and why the admin role is required on top of it.

---

## Monitoring and Alerting

Prometheus scrapes every 15 seconds across four jobs: the on-premises node exporter, cAdvisor, the EC2 nodes, and the application's `/metrics` endpoint. The EC2 and application targets are file-based service discovery, and `deploy.sh` rewrites those JSON files after each apply.

### Alert rules

| Alert | Expression | For | Severity |
|---|---|---|---|
| HighCPU | CPU above 80% | 2m | warning |
| HighMemory | memory above 85% | 2m | warning |
| NodeDown | `up{job="ec2-nodes"} == 0` | 1m | critical |
| FastAPIDown | `up{job="fastapi-app"} == 0` | 1m | critical |

Alertmanager groups by alert name, instance and severity, waits 30 seconds, and repeats every 4 hours. One receiver fans out to the `#shimonvault-alerts` Slack channel and to the Telegram relay, which exists because Alertmanager has no native Telegram support. An inhibit rule suppresses HighCPU, HighMemory and FastAPIDown on any instance already reporting NodeDown, so one dead host sends one alert instead of four.

Alertmanager does not expand environment variables inside its own configuration file, so the compose entrypoint writes the Slack webhook URL to `/tmp/slack_url` at startup and the config reads it with `slack_api_url_file`.

### CloudWatch alarms

| Alarm | Watches | Action |
|---|---|---|
| high-cpu | ASG CPU above 80% for 2 periods | scale-out policy and the infra-alert topic |
| instance-status-check | EC2 status check failures | infra-alert topic |
| alb-5xx-errors | ALB 5xx count | infra-alert topic |
| high-cpu-asg | ASG CPU high | scale out |
| low-cpu-asg | ASG CPU low | scale in |

### Grafana

Two provisioned dashboards: `infra_health` for the node and container metrics, and `auditstream` for the security event view.

---

## Delivery

### CI, on every push and every pull request to main

flake8 at 120 columns → pytest against SQLite in memory with a 50 percent coverage floor → a Docker build check that never pushes. The build check runs the full multi-stage Dockerfile, which means the Vite frontend build is verified too.

### CD, dispatched by hand

```
build and push  mindmug/shimonvault-app:green  and  :green-<sha>   (amd64 and arm64)
      ↓
Slack: deployment started
      ↓
terraform apply -var deploy_green=true          green instance up, listener still on blue
      ↓
poll describe-target-health on the green target group, 40 attempts at 15s
      ↓
terraform apply -var deploy_green=true -var active_color=green      the switch
      ↓
retag :green as :blue
      ↓
Slack: complete, or failed with blue still live
```

`cd.yml` is `workflow_dispatch` only. It ran on every push to main until that trigger rebuilt live AWS infrastructure after a `terraform destroy` and started the billing again with nobody watching, so deploying is now an explicit `gh workflow run cd.yml --ref main`. CI still runs on every push, because linting and testing cost nothing.

A concurrency group named `deploy-production` with `cancel-in-progress: false` makes sure two deploys never run at once and no deploy is ever cancelled mid-flight.

The switch is a Terraform variable rather than an `aws elbv2 modify-listener` call. A CLI switch is drift: the next `terraform apply` quietly puts traffic back on blue and nobody knows why. Making the listener target a variable puts the switch in state, and the pipeline only reaches it after the green target group has actually reported healthy.

A rollback is the same apply with `active_color=blue`, so it goes through the same variable and leaves no drift behind it.

---

## API Reference

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/auth/register` | public | defaults to the viewer role |
| POST | `/auth/login` | public | 10 per minute per IP |
| POST | `/auth/logout` | any | client-side token discard |
| POST | `/docs/upload` | admin, editor | triggers validate_file through S3 |
| GET | `/docs/list` | any | |
| GET | `/docs/download/{doc_id}` | any | 10 per 60 seconds per IP, presigned URL |
| DELETE | `/docs/{doc_id}` | admin, editor | soft delete |
| GET | `/docs/{doc_id}/versions` | any | |
| POST | `/meetings/create` | admin, editor | registers two EventBridge rules |
| GET | `/meetings/list` | any | |
| GET | `/meetings/{id}` | participant | |
| PUT | `/meetings/{id}` | organizer | |
| DELETE | `/meetings/{id}` | organizer | removes the EventBridge rules |
| POST | `/meetings/{id}/join` | participant | join token required |
| GET | `/meetings/{id}/archive` | organizer | attendance record |
| GET | `/audit/feed` | admin | the live AuditStream |
| GET | `/audit/incidents` | admin | |
| GET | `/audit/my-activity` | any | own events only |
| GET | `/admin/metrics/summary` | admin | headline numbers |
| GET | `/admin/metrics/timeseries` | admin | per-minute counts |
| GET | `/admin/metrics/infra` | admin | read through the Prometheus HTTP API |
| POST | `/demo/*` | admin | five simulations, gated by `DEMO_ENABLED` |
| GET | `/health` | public | always 200, with a `db` field carrying the real state |
| GET | `/metrics` | public | Prometheus format |

### Why `/health` returns 200 before the database is ready

RDS takes 30 to 60 seconds to answer after the instance boots, and the ALB marks a target unhealthy long before that. Initialising the schema during startup meant a deploy never went green. `init_db()` now runs in a daemon thread that retries 20 times at 15 seconds, and `/health` answers 200 immediately with a `db` field that reads `initialising`, then `ok`, then the error text if it fails. The ALB reads the status code. A human reads the body.

---

## Data Model

PostgreSQL, five tables, UUID primary keys throughout. Sequential integers let an attacker enumerate records by incrementing an ID.

| Table | Holds |
|---|---|
| `users` | email, username, bcrypt hash, role, is_active, suspended |
| `documents` | filename, S3 key, content type, size, version, parent version, owner, status |
| `meetings` | title, organizer, join token, status, scheduled and end times, EventBridge rule name |
| `participants` | meeting, user, attended flag, join time |
| `audit_events` | event type, user, IP, resource, detail JSON, severity, timestamp |

DynamoDB, three tables, all on-demand billing:

| Table | Keys | Notes |
|---|---|---|
| `audit-log` | id / created_at | GSI on `event_type`, 90-day TTL |
| `incidents` | id / created_at | the dedicated incident view |
| `meetings` | meeting_id | read by the two meeting Lambdas |

The audit trail is written to both. DynamoDB serves the fast queries the console makes, and PostgreSQL keeps the relational copy for reporting.

### Read and write split

`WRITE_DB_URL` points at the RDS primary and takes every mutation. `READ_DB_URL` points at the on-premises replica on `proj-ubuntu01:5433` and takes the select-only routes. Both engines are created lazily with `pool_pre_ping`, a 30-minute recycle and a 10-second connect timeout. `setup_replica.sh` sets up the subscription over Tailscale, reaching RDS through a socat relay on the app instance rather than through the bastion, so replication survives a bastion that is down.

The URL scheme must be `postgresql+psycopg2`. asyncpg fails at runtime rather than at import, with a `MissingGreenlet` error that says nothing about the driver.

---

## Configuration

Nothing is hardcoded. `app/.env` is generated by `generate_env.sh` from Terraform outputs after every apply.

### Application environment

| Group | Variables |
|---|---|
| Identity | `PROJECT_NAME`, `APP_VERSION`, `ENVIRONMENT` |
| Database | `WRITE_DB_URL`, `READ_DB_URL` |
| Auth | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` |
| AWS | `AWS_REGION`, `AWS_ACCOUNT_ID` |
| S3 | `S3_BUCKET_DOCS`, `S3_BUCKET_REPORTS`, `S3_PRESIGNED_URL_EXPIRY` |
| DynamoDB | `DYNAMODB_AUDIT_TABLE`, `DYNAMODB_INCIDENTS_TABLE`, `DYNAMODB_MEETINGS_TABLE` |
| SNS | `SNS_TOPIC_SECURITY_ALERT`, `SNS_TOPIC_INFRA_ALERT`, `SNS_TOPIC_MEETING_REMINDERS` |
| Notifications | `SLACK_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Monitoring | `PROMETHEUS_URL` |
| Rate limits | `RATE_LIMIT_LOGIN`, `RATE_LIMIT_DOWNLOAD`, `RATE_LIMIT_DEFAULT` |
| Demo | `DEMO_ENABLED`, `DEMO_BASE_URL`, `DEMO_ATTACKER_IP`, and the per-scenario counts |

### GitHub Actions secrets

| Secret | Where it comes from |
|---|---|
| `AWS_ACCESS_KEY_ID` · `AWS_SECRET_ACCESS_KEY` | IAM user security credentials |
| `DOCKERHUB_USERNAME` · `DOCKERHUB_TOKEN` | Docker Hub access token |
| `DB_PASSWORD` · `JWT_SECRET_KEY` | the same values as `terraform.tfvars` |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook |
| `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` | BotFather, then getUpdates |
| `ALERT_EMAIL` · `YOUR_IP_CIDR` | the SNS email subscription and the bastion rule |
| `TAILSCALE_AUTH_KEY` · `ONPREM_TAILSCALE_IP` | Tailscale admin console |
| `SSH_PUBLIC_KEY` | the public half of the deploy key |

Every secret is passed to Terraform as a `TF_VAR_` at job level, so both apply steps in the deploy see the same values.

### Demo accounts

Seeded from `db/seed.sql`, one per role: `admin@shimonvault.com`, `editor@shimonvault.com`, `viewer@shimonvault.com`. These are demo credentials for a build that is destroyed at the end of every session, and the demo router still reads them from the environment so nothing is truly hardcoded.

---

## Tech Stack

- **Cloud:** AWS (VPC, EC2, ALB, RDS, S3, DynamoDB, Lambda, SNS, EventBridge, CloudWatch, IAM, NACL)
- **Hybrid connectivity:** Tailscale (mesh, zero public ports on either side)
- **DNS:** Cloudflare, DNS only. **TLS:** ACM on the ALB, DNS-validated through the same zone
- **IaC:** Terraform 1.7, S3 backend with a DynamoDB lock
- **Configuration management:** Ansible, with dynamic EC2 inventory
- **Containers:** Docker, multi-stage and multi-platform (amd64 and arm64), Docker Hub
- **App:** FastAPI, Python 3.12, SQLAlchemy, slowapi, python-jose, passlib
- **Frontend:** React, Vite, Chart.js
- **Database:** PostgreSQL 16 on RDS, logical replication to an on-premises replica
- **Monitoring:** Prometheus, Grafana, Alertmanager, node exporter, cAdvisor, Portainer
- **Alerting:** Slack, Telegram
- **CI/CD:** GitHub Actions, blue/green through a Terraform variable

## Testing

```bash
cd app && pip install -r requirements.txt pytest pytest-cov && cd ..
pytest tests/ -v
```

Tests run against SQLite in memory and need no AWS credentials. `conftest.py` sets every environment variable before the first application import, overrides both database dependencies and bypasses the rate limiter, so a test never depends on wall-clock timing.

Coverage is enforced in CI at 50 percent. The suite covers authentication (registration, login, wrong password, unknown email, token acceptance, missing token) and auditing (middleware firing on every request, `/health` staying out of the log, failed logins recorded at warning severity, admin-only incident access).

---

## Known Gaps

Written down rather than left to be discovered.

- The SNS publish on credential stuffing is still a TODO. `block_ip` is deployed, subscribed to the security-alert topic and IAM-authorised, and the application currently writes the incident and sends the alerts directly instead of publishing. The automatic block therefore has no live trigger from the login path.
- `block_ip` no-ops when `NACL_ID` is unset. It logs a warning and returns, which is a silent failure in exactly the path that is supposed to be automatic.
- All the counters are in-process. The exfiltration window, the suspension count and the login-failure count live in module-level dictionaries. Two application instances count separately, and a restart forgets everything. Redis or DynamoDB is the right home for them.
- The test folder is smaller than it looks. `tests/test_docs.py` and `tests/test_meetings.py` are copies of their router source rather than tests, so the real suite is 15 tests over auth and audit.
- Rejected uploads are deleted after they land. `validate_file` runs on `ObjectCreated:Put`, so the file is in the bucket for the moment it takes to check. A quarantine bucket with a promotion step would close that window.
- The Auto Scaling group is a demonstration, not the serving path. It sits at `desired_capacity = 0` with its launch template, both scaling policies and both CPU alarms intact. Blue/green is what actually serves traffic.
- Prometheus targets are files, not discovery. `deploy.sh` rewrites `targets/*.json` after each apply, where EC2 service discovery would remove the step.

### One bug worth recording

The bulk-download simulation never produced a 429 while it requested 50 different document IDs, and produced one immediately when it requested the same ID repeatedly. slowapi's default `key_style="url"` keys the counter on the resolved URL, so `/docs/download/doc-0001` and `/docs/download/doc-0002` are different keys and neither ever reaches 2. Setting `key_style="endpoint"` keys on the route function instead, which is shared across every value of `{doc_id}`. The limiter had been decorating the route correctly the whole time and counting the wrong thing.
