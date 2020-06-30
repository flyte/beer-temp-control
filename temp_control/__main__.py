import argparse
import logging.config
import sys

import yaml

from . import Server


def main():
    p = argparse.ArgumentParser()
    p.add_argument("config")
    args = p.parse_args()

    # Load, validate and normalise config, or quit.
    try:
        config = yaml.safe_load(open(args.config))
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if "logging" in config:
        logging.config.dictConfig(config["logging"])

    server = Server(config)
    server.run()


if __name__ == "__main__":
    main()
