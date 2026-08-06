# NovaBank Demo Data Dictionary

Fictional organization only. Production-ineligible.

| Concept | Storage | Natural key pattern | Notes |
|---|---|---|---|
| Organization | `ent_organizations` | `org` / `novabank` | Single tenant org |
| Business unit | `ent_business_units` | `bu` / code | 5 BUs; foundational codes preserved |
| Department | `ent_departments` | `dept` / code | 10 departments |
| Team | `ent_teams` | `team` / slug | 10 teams |
| Engineer | `ent_engineer_profiles` | `eng` / eng-NN | 48 fictional profiles |
| Capability | `ent_capabilities` | `cap` / slug | 18 capabilities |
| Skill | `ent_skills` | `skill` / slug | 16 skills |
| Initiative | `ent_initiatives` | `init` / slug | 14 initiatives |
| Project | `ent_projects` | `proj` / slug | 24 projects |
| Repository | `ent_repositories` | `repo` / github / novabank/name | 32 repos |
| Sprint | `ent_sprints` | `sprint` / team_id / name | 30 sprints |
| Work item | `ent_work_items` | `wi` / jira / NB-* | 480 items |
| Pull request | `ent_pull_requests` | `pr` / github / repo / pr-NNNN | 220 PRs |
| Deployment | `ent_deployments` | `deploy` / github / deploy-N | 75 deploys |
| Incident | `ent_incidents` | `inc` / manual / INC-* | 32 incidents |
| Dependency | `ent_dependencies` | `dep` / types+ids | 58 edges |
| Ownership | `ent_ownerships` | `own` / owner+resource | 120 rows |
| Availability | `ent_availabilities` | `avail` / target+start | 18 windows |
| Manifest | `ent_evidence_signals` | signal_type=`demo_dataset_manifest` | Hashed inventory |
| Story scenarios | `ent_scenario_*` | STORY-0N names | 8 definitions |

Availability `reason` values are limited to `planned_leave`, `allocation`,
`incident_response`. No personal leave reasons are stored.

## Temporal and graph materialization

| Field | Rule |
|---|---|
| `AS_OF_AT` | `2026-07-31T18:00:00Z` — all observed evidence is at or before this anchor |
| `FOUNDATIONAL_BASE` | `2026-01-06T09:00:00Z` — org/portfolio seed start |
| Closed intervals | `valid_from < valid_to` (`ck_ent_dge_valid_interval` preserved) |
| Open intervals | `valid_to IS NULL` |
| Derived team→initiative supports | Natural key includes `project_id` (no multi-project payload flip) |
| Graph rebuild | Mandatory for materialize success; second rebuild idempotent |
| Story 7 brief | Grounded deterministic-fallback CoS brief with citation binding |

Portfolio `created_at` / `planned_start` are seeded from `dt_from_base` /
`FOUNDATIONAL_BASE` (no wall-clock generation timestamps).
