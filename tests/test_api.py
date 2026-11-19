from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from ledger.serve import server


def test_only_known_queries_reach_databases_and_missing_receipt_returns_503(tmp_path):
    with server(0, tmp_path / "missing.json") as http:
        thread = Thread(target=http.serve_forever, daemon=True)
        thread.start()
        root = f"http://127.0.0.1:{http.server_port}"
        try:
            for path, status in [
                ("/api/compare/unknown", 404),
                ("/api/report", 503),
                ("/../../.git/config", 404),
            ]:
                with pytest.raises(HTTPError) as exc:
                    urlopen(root + path)
                assert exc.value.code == status
        finally:
            http.shutdown()
            thread.join()
