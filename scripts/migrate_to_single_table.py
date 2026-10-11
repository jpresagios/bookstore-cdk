"""Copy Books and Presales into Bookstore.

Run this after Bookstore exists. The old tables stay in place.

    python scripts/migrate_to_single_table.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bookstore_cdk" / "crud"))

from migrate import main  # noqa: E402

if __name__ == "__main__":
    main()
