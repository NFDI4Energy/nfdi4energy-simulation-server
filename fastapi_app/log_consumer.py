"""Compatibility launcher for the DaceDSX event consumer."""
from fastapi_app.frameworks.dacedsx.events.consumer import main


if __name__ == "__main__":
    import sys

    try:
        main()
    except Exception as exc:
        print(f"[log-consumer] fatal error: {exc}", flush=True)
        sys.exit(1)
