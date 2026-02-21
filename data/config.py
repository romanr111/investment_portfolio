import yaml
import os
from pathlib import Path


def load_ib_config():
    """Load Interactive Brokers configuration from the client portal gateway config file."""
    default_config = {"port": 5050, "host": "localhost"}
    try:
        # Prefer explicit env path, then repo-local and known legacy locations.
        repo_root = Path(__file__).resolve().parents[1]
        candidate_paths = []

        env_config_path = os.getenv("IB_GATEWAY_CONF")
        if env_config_path:
            candidate_paths.append(Path(os.path.expanduser(env_config_path)))

        candidate_paths.extend(
            [
                repo_root / "clientportal.gw" / "root" / "conf.yaml",
                Path.home()
                / "Documents"
                / "Development"
                / "investment_portfolio"
                / "clientportal.gw"
                / "root"
                / "conf.yaml",
                Path.home()
                / "Documents"
                / "Development"
                / "Portfolio"
                / "clientportal.gw"
                / "root"
                / "conf.yaml",
            ]
        )

        config_path = next((path for path in candidate_paths if path.exists()), None)
        if config_path is None:
            raise FileNotFoundError("Could not locate clientportal.gw/root/conf.yaml")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        # Extract the port from the configuration
        port = int(config.get("listenPort", default_config["port"]))

        return {"port": port, "host": "localhost"}
    except Exception as e:
        print(f"Warning: Could not load IB config: {e}")
        # Return default values if config file cannot be read
        return default_config
