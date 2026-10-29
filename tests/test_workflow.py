"""自动更新流程（.github/workflows/deploy.yml）的检查。"""

from pathlib import Path

WORKFLOW = (Path(__file__).parent.parent / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")


def test_schedule_avoids_the_top_of_the_hour():
    assert 'cron: "7,27,47 * * * *"' in WORKFLOW
    assert '"0 ' not in WORKFLOW and "*/20" not in WORKFLOW


def test_keepalive_reenables_the_schedule():
    assert "keepalive:" in WORKFLOW
    assert "actions: write" in WORKFLOW
    assert 'gh api -X PUT "repos/${{ github.repository }}/actions/workflows/deploy.yml/enable"' in WORKFLOW


def test_keepalive_does_not_block_deploy():
    # 发布只依赖 build，保活失败也不影响更新网页
    deploy = WORKFLOW[WORKFLOW.index("  deploy:"):]
    assert "needs: build" in deploy


def test_tests_run_before_building_the_page():
    assert WORKFLOW.index("pytest -q") < WORKFLOW.index("python build.py")
    assert WORKFLOW.index("node --test") < WORKFLOW.index("python build.py")
    assert "ICS_URL: ${{ secrets.ICS_URL }}" in WORKFLOW
