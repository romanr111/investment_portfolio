import os

from src import portfolio_sync


def test_load_local_env_file_reads_export_lines_without_overriding(monkeypatch, tmp_path):
    env_file = tmp_path / "ib_flex_env.sh"
    env_file.write_text(
        "\n".join(
            [
                "# local config",
                "export IB_FLEX_TOKEN='secret-token'",
                'export IB_ACCOUNT_ID="DU123"',
                "export EXISTING_VALUE=from-file",
            ]
        )
    )
    monkeypatch.delenv("IB_FLEX_TOKEN", raising=False)
    monkeypatch.delenv("IB_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("EXISTING_VALUE", "from-env")

    portfolio_sync._load_local_env_file(env_file)

    assert os.environ["IB_FLEX_TOKEN"] == "secret-token"
    assert os.environ["IB_ACCOUNT_ID"] == "DU123"
    assert os.environ["EXISTING_VALUE"] == "from-env"


def test_venv_python_points_inside_project_venv():
    python_path = portfolio_sync._venv_python()

    assert ".venv" in python_path.parts
