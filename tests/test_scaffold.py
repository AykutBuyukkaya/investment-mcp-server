from investment_mcp_server.settings import Settings
from investment_mcp_server.server import _validate_transport


def test_default_transport_is_streamable_http() -> None:
    assert Settings().transport == "streamable-http"


def test_validate_transport_accepts_stdio() -> None:
    assert _validate_transport("stdio") == "stdio"


def test_validate_transport_rejects_unknown_value() -> None:
    try:
        _validate_transport("websocket")
    except ValueError as exc:
        assert "Unsupported MCP transport" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported transport")
