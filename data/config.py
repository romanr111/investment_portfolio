import yaml
import os


def load_ib_config():
    """Load Interactive Brokers configuration from the client portal gateway config file."""
    try:
        # Path to the client portal gateway config file
        config_path = os.path.expanduser(
            "~/Documents/Development/Portfolio/clientportal.gw/root/conf.yaml"
        )

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Extract the port from the configuration
        port = config.get("listenPort", 5050)  # Default to 5050 if not found

        return {"port": port, "host": "localhost"}
    except Exception as e:
        print(f"Warning: Could not load IB config: {e}")
        # Return default values if config file cannot be read
        return {"port": 5050, "host": "localhost"}
