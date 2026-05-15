"""Backwards-compat shim — the project pivoted from event-sponsor matching to
company tender-hunting. Use seed_company instead."""
from sponsorus.scripts.seed_company import main


if __name__ == "__main__":
    main()
