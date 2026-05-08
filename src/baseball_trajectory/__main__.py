"""Console entry point for the baseball-trajectory Shiny app."""

import shiny

from baseball_trajectory.app import app


def main() -> None:
    shiny.run_app(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
