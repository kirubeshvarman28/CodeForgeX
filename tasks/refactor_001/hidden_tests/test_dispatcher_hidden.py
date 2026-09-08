"""Hidden verification tests for RequestDispatcher."""

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


def test_default_xml_and_form_handlers():
    """Verify built-in XML and Form handlers operate correctly via strategy pattern."""
    dispatcher = RequestDispatcher()

    # XML
    xml_req = Request(path="/xml", content_type="application/xml", body="<data><item/></data>")
    xml_res = dispatcher.dispatch(xml_req)
    assert xml_res.status_code == 200
    assert xml_res.body == "data"

    # Form
    form_req = Request(path="/form", content_type="application/x-www-form-urlencoded", body="user=john&role=admin")
    form_res = dispatcher.dispatch(form_req)
    assert form_res.status_code == 200
    assert form_res.body == {"user": "john", "role": "admin"}


def test_malformed_json_error_status():
    """Verify malformed JSON payload returns 400 with error details."""
    dispatcher = RequestDispatcher()
    bad_req = Request(path="/api", content_type="application/json", body="{bad json")
    bad_res = dispatcher.dispatch(bad_req)

    assert bad_res.status_code == 400
    assert "error" in bad_res.body


def test_custom_handler_precedence_override():
    """Verify custom handler registered for existing content-type takes precedence."""
    class CustomJsonOverrideHandler(BaseRequestHandler):
        def can_handle(self, request: Request) -> bool:
            return request.content_type == "application/json"

        def handle(self, request: Request) -> Response:
            return Response(status_code=200, content_type="application/json", body={"intercepted": True})

    dispatcher = RequestDispatcher()
    # Prepend or register custom handler
    dispatcher.register_handler(CustomJsonOverrideHandler(), prepend=True)

    req = Request(path="/test", content_type="application/json", body='{"a": 1}')
    res = dispatcher.dispatch(req)
    assert res.body == {"intercepted": True}
