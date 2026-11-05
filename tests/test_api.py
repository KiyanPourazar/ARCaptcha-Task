from __future__ import annotations

from unittest.mock import patch

from app.db.models import BotRun, RunStatus


def test_list_bots(client):
    response = client.get("/api/bots")
    assert response.status_code == 200
    bots = response.json()["bots"]
    assert any(b["id"] == "arcaptcha_demo_selenium" for b in bots)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_launch_and_history(client, db_session):
    with patch("app.api.routes._run_in_background"):
        launched = client.post(
            "/api/runs",
            json={"bot_id": "arcaptcha_demo_selenium", "browser_mode": "headless"},
        )
        assert launched.status_code == 202
        run_id = launched.json()["run"]["id"]

    run = db_session.get(BotRun, run_id)
    assert run is not None
    run.status = RunStatus.SUCCESS
    run.challenge_id = "tok-api-1"
    run.result_message = "ok"
    db_session.commit()

    history = client.get("/api/runs")
    assert history.status_code == 200
    runs = history.json()["runs"]
    assert any(r["id"] == run_id for r in runs)

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["challenge_id"] == "tok-api-1"
    assert detail.json()["status"] == "success"


def test_unknown_bot_rejected(client):
    response = client.post(
        "/api/runs",
        json={"bot_id": "does_not_exist", "browser_mode": "headful"},
    )
    assert response.status_code == 404
