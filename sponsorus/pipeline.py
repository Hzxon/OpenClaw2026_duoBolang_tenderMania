"""Pipeline alias for `python3 -m sponsorus.pipeline` ergonomics."""
from sponsorus.run_pipeline import main, run_pipeline  # noqa: F401

if __name__ == "__main__":
    main()
