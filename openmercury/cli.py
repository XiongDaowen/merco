"""OpenMercury CLI entry point."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="openmercury",
        description="AI-driven self-improving development platform",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="openmercury 0.1.0",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="~/.openmercury/config.json",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--mode",
        choices=["tui", "headless", "web"],
        default="tui",
        help="Running mode",
    )

    args = parser.parse_args()
    print(f"OpenMercury v0.1.0 - Mode: {args.mode}")


if __name__ == "__main__":
    main()
