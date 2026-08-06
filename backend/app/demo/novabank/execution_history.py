"""Execution history: sprints, work items, PRs, deployments, incidents."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import enterprise as orm
from app.demo.novabank import identities as idn
from app.demo.novabank.distributions import bounded_title, choose, choose_weighted, stable_int
from app.demo.novabank.helpers import clamp_observed, dt_from_base, ensure, tid
from app.demo.novabank.specification import TARGET_INVENTORY


def seed_execution_history(session: Session, ids: dict[str, str], summary: dict[str, int]) -> None:
    team_slugs = [t[1] for t in idn.TEAMS]
    project_slugs = [p[1] for p in idn.PROJECTS]
    repo_names = [r[0] for r in idn.REPOSITORIES]

    # 30 sprints across teams (foundational used Sprint 1..6 on rotating teams).
    for sprint_index in range(TARGET_INVENTORY["sprints"]):
        team_slug = team_slugs[sprint_index % len(team_slugs)]
        name = f"Sprint {sprint_index + 1}"
        sprint_id = tid("sprint", ids[f"team:{team_slug}"], name)
        ids[f"sprint:{sprint_index}"] = sprint_id
        start = dt_from_base(sprint_index * 7)
        end = dt_from_base(sprint_index * 7 + 14)
        state = "closed" if sprint_index < 24 else "active"
        summary["sprints"] += ensure(
            session,
            orm.Sprint,
            sprint_id,
            {
                "sprint_id": sprint_id,
                "team_id": ids[f"team:{team_slug}"],
                "name": name,
                "start_time": start,
                "end_time": end,
                "state": state,
            },
        )

    statuses = ["backlog", "in_progress", "in_review", "done", "blocked"]
    status_weights = [20, 25, 15, 30, 10]
    priorities = ["p0", "p1", "p2", "p3"]
    types = ["story", "task", "bug", "spike"]
    blocked_projects = {"rt-payments-rail", "fraud-scoring-v2", "ledger-modernization"}

    for n in range(TARGET_INVENTORY["work_items"]):
        # Preserve foundational NB-100..NB-129 natural keys for first 30.
        if n < 30:
            ref = f"NB-{100 + n}"
            proj_slug = project_slugs[n % 8]  # foundational project set size
        else:
            ref = f"NB-{1000 + (n - 30)}"
            proj_slug = project_slugs[n % len(project_slugs)]
        wi_id = tid("wi", "jira", ref)
        status = choose_weighted(statuses, status_weights, "wi-status", ref)
        if proj_slug in blocked_projects and n % 11 == 0:
            status = "blocked"
        created = dt_from_base(n % 180)
        updated = clamp_observed(dt_from_base((n % 180), 4 + (n % 5)))
        completed = clamp_observed(dt_from_base((n % 180), 8)) if status == "done" else None
        title = bounded_title(f"{proj_slug} work", n)
        summary["work_items"] += ensure(
            session,
            orm.WorkItem,
            wi_id,
            {
                "work_item_id": wi_id,
                "enterprise_project_id": ids[f"proj:{proj_slug}"],
                "sprint_id": ids[f"sprint:{n % TARGET_INVENTORY['sprints']}"],
                "provider": "jira",
                "external_reference": ref,
                "title": title,
                "work_item_type": types[n % len(types)],
                "status": status,
                "priority": priorities[n % len(priorities)],
                "source_created_at": created,
                "source_updated_at": updated,
                "completed_at": completed,
            },
        )

    # Pull requests — dedicated table. Concentrated authors on CONCENTRATED_REPOS.
    eng_keys = [e[1] for e in idn.ENGINEERS]
    for n in range(TARGET_INVENTORY["pull_requests"]):
        if n < 40:
            repo_name = choose(idn.CONCENTRATED_REPOS, "pr-conc", str(n))
            author = (
                "eng-13" if n % 3 else choose(("eng-12", "eng-13", "eng-14"), "pr-auth", str(n))
            )
            review_lag_hours = 48 + (n % 24)
        else:
            repo_name = repo_names[n % len(repo_names)]
            author = eng_keys[n % len(eng_keys)]
            review_lag_hours = 4 + (n % 20)
            if repo_name in idn.CONCENTRATED_REPOS:
                review_lag_hours = 36 + (n % 30)
        external_id = f"pr-{n + 1:04d}"
        pr_id = tid("pr", "github", ids[f"repo:{repo_name}"], external_id)
        created = dt_from_base((n * 2) % 170)
        updated = clamp_observed(dt_from_base((n * 2) % 170, review_lag_hours))
        state = choose_weighted(
            ["merged", "open", "closed"],
            [70, 20, 10],
            "pr-state",
            external_id,
        )
        merged_at = updated if state == "merged" else None
        closed_at = updated if state in {"merged", "closed"} else None
        summary["pull_requests"] += ensure(
            session,
            orm.PullRequest,
            pr_id,
            {
                "pull_request_id": pr_id,
                "repository_id": ids[f"repo:{repo_name}"],
                "provider": "github",
                "external_id": external_id,
                "number": n + 1,
                "title": bounded_title(f"{repo_name} change", n, max_len=200),
                "state": state,
                "draft": False,
                "author_external_id": f"synthetic-{author}",
                "created_at_source": created,
                "updated_at_source": updated,
                "closed_at_source": closed_at,
                "merged_at_source": merged_at,
                "additions": 10 + stable_int("pr-add", external_id, modulo=400),
                "deletions": 5 + stable_int("pr-del", external_id, modulo=200),
                "changed_files": 1 + stable_int("pr-files", external_id, modulo=25),
                "source_precedence": "seed",
            },
        )

    # Deployments: higher frequency for mature platform repos.
    mature = {"cloud-landing-zone", "payments-core-svc", "slo-controller", "identity-gateway"}
    for n in range(TARGET_INVENTORY["deployments"]):
        if n < 40:
            repo_name = choose(tuple(sorted(mature)), "deploy-mature", str(n))
        else:
            repo_name = repo_names[n % len(repo_names)]
        ref = f"deploy-{300 + n}"
        dep_id = tid("deploy", "github", ref)
        started = dt_from_base(20 + (n % 150))
        completed = clamp_observed(dt_from_base(20 + (n % 150), 1))
        # Associate some failures with elevated-incident repos.
        if repo_name in idn.ELEVATED_INCIDENT_REPOS and n % 5 == 0:
            status = "failed"
        else:
            status = "succeeded" if n % 4 else "failed"
        summary["deployments"] += ensure(
            session,
            orm.Deployment,
            dep_id,
            {
                "deployment_id": dep_id,
                "repository_id": ids[f"repo:{repo_name}"],
                "provider": "github",
                "external_reference": ref,
                "environment": "production" if n % 2 == 0 else "staging",
                "status": status,
                "started_at": started,
                "completed_at": completed,
            },
        )

    # Incidents: mostly sev3/sev4, fewer sev2, very few sev1. Spike near as_of.
    severities = ["sev4", "sev3", "sev2", "sev1"]
    sev_weights = [45, 35, 15, 5]
    for n in range(TARGET_INVENTORY["incidents"]):
        if n < 5:
            # Preserve foundational INC-200.. and INC-PLATFORM-500 via same natural keys
            # for the first four; fifth is platform (handled separately in relationships
            # path). Here we still create INC-200.. using foundational refs for n<4.
            ref = f"INC-{200 + n}" if n < 4 else "INC-PLATFORM-500"
            repo_name = idn.REPOSITORIES[n % 10][0] if n < 4 else "payments-core-svc"
            severity = ["sev1", "sev2", "sev3", "sev4"][n % 4] if n < 4 else "sev1"
            started = dt_from_base(20 + n if n < 4 else 25)
            resolved = None if n == 4 else clamp_observed(dt_from_base(20 + n, 6))
            state = "open" if n == 4 else "resolved"
            team_id = ids["team:cloud-foundations"] if n == 4 else None
        else:
            ref = f"INC-{500 + n}"
            # Spike: later incidents concentrate on elevated repos near as_of.
            if n >= 20:
                repo_name = choose(idn.ELEVATED_INCIDENT_REPOS, "inc-spike", str(n))
                start_day = 160 + (n % 20)
            else:
                repo_name = repo_names[n % len(repo_names)]
                start_day = 30 + n * 3
            severity = choose_weighted(severities, sev_weights, "inc-sev", ref)
            started = dt_from_base(start_day)
            resolved = clamp_observed(dt_from_base(start_day, 4 + (n % 10)))
            if resolved < started:
                resolved = started
            state = "resolved"
            team_id = ids[
                f"team:{idn.REPOSITORIES[[r[0] for r in idn.REPOSITORIES].index(repo_name)][1]}"
            ]
        inc_id = tid("inc", "manual", ref)
        summary["incidents"] += ensure(
            session,
            orm.Incident,
            inc_id,
            {
                "incident_id": inc_id,
                "repository_id": ids[f"repo:{repo_name}"],
                "team_id": team_id,
                "provider": "manual",
                "external_reference": ref,
                "severity": severity,
                "started_at": started,
                "resolved_at": resolved,
                "state": state,
            },
        )
