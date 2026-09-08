"""Monolithic Request Dispatcher module."""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import parse_qs


class UnsupportedContentTypeError(Exception):
    """Raised when a request specifies an unsupported Content-Type."""
    pass


@dataclass
class Request:
    """Incoming HTTP-like request model."""
    path: str
    content_type: str
    body: str = ""
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class Response:
    """Dispatched response model."""
    status_code: int
    content_type: str
    body: Any


class RequestDispatcher:
    """Monolithic request dispatcher handling content types via rigid if-else branches."""

    def dispatch(self, request: Request) -> Response:
        """Process incoming request and return structured response."""
        ct = (request.content_type or "").lower().strip()

        if ct == "application/json":
            try:
                parsed = json.loads(request.body) if request.body else {}
                return Response(status_code=200, content_type="application/json", body=parsed)
            except Exception as e:
                return Response(status_code=400, content_type="application/json", body={"error": str(e)})

        elif ct in ("application/xml", "text/xml"):
            try:
                root = ET.fromstring(request.body) if request.body else ET.Element("empty")
                return Response(status_code=200, content_type="application/xml", body=root.tag)
            except Exception as e:
                return Response(status_code=400, content_type="application/xml", body=f"XML Error: {e}")

        elif ct == "application/x-www-form-urlencoded":
            parsed = parse_qs(request.body)
            # Flatten single values
            flattened = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            return Response(status_code=200, content_type="application/json", body=flattened)

        else:
            raise UnsupportedContentTypeError(f"Unsupported content type: '{request.content_type}'")
