import json
import os

def load_config(base_dir, config_file):
    config_path = os.path.join(base_dir, config_file)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config