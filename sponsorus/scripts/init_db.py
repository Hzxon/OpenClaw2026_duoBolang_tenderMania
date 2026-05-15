"""One-shot DB initialization."""
from sponsorus import db


def main() -> None:
    db.init_db()
    print(f"DB initialized at {db.DB_PATH}")


if __name__ == "__main__":
    main()
