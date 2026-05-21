import json

from chargeback_copilot import api


if __name__ == "__main__":
    print(json.dumps(api.readiness(), indent=2))
