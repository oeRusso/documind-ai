"""The worker process starts with only its own imports: it must know every table anyway.

Regression: the worker failed with NoReferencedTableError when inserting chunks, because the
documents and organizations models were never imported in that process.
"""

import subprocess
import sys


def test_worker_module_registers_all_tables() -> None:
    code = (
        "import os; os.environ['CELERY_BROKER_URL'] = 'redis://localhost:1/0'\n"
        "import app.worker\n"
        "from app.infrastructure.database.base import Base\n"
        "tables = set(Base.metadata.tables)\n"
        "assert {'organizations', 'documents', 'document_versions', 'document_chunks'} <= tables\n"
        "for table in Base.metadata.sorted_tables:\n"
        "    for fk in table.foreign_keys:\n"
        "        fk.column  # raises NoReferencedTableError if a referenced table is unknown\n"
    )
    # A fresh interpreter (nothing imported by other tests), running fixed code: S603 is moot.
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr[-2000:]
