"""Public tests for RequestDispatcher and Strategy Pattern."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from dispatcher import (
    BaseRequestHandler,
    Request,
    RequestDispatcher,
    Response,
    UnsupportedContentTypeError,
)


def test_backward_compatibility_json_dispatch():
    """Verify legacy JSON request dispatching continues to work identically."""
    dispatcher = RequestDispatcher()
    req = Request(path="/api/data", content_type="application/json", body='{"name": "Alice"}')
    res = dispatcher.dispatch(req)

    assert res.status_code == 200
    assert res.content_type == "application/json"
    assert res.body == {"name": "Alice"}


def test_backward_compatibility_unsupported_type_raises():
    """Verify unknown content types raise UnsupportedContentTypeError."""
    dispatcher = RequestDispatcher()
    req = Request(path="/upload", content_type="application/octet-stream", body="binary")

    with pytest.raises(UnsupportedContentTypeError):
        dispatcher.dispatch(req)


def test_pluggable_custom_handler_registration():
    """Verify custom handler can be implemented and registered dynamically."""
    class CustomCsvHandler(BaseRequestHandler):
        def can_handle(self, request: Request) -> bool:
            return request.content_type == "text/csv"

        def handle(self, request: Request) -> Response:
            lines = [l.strip().split(",") for l in request.body.strip().splitlines() if l.strip()]
            return Response(status_code=200, content_type="application/json", body=lines)

    dispatcher = RequestDispatcher()
    dispatcher.register_handler(CustomCsvHandler())

    req = Request(path="/import", content_type="text/csv", body="a,b\n1,2")
    res = dispatcher.dispatch(req)

    assert res.status_code == 200
    assert res.body == [["a", "b"], ["1", "2"]]
