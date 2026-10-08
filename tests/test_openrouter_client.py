"""The real OpenRouterClient against a fake HTTP transport: no network, no real key."""
import json

import httpx
import pytest

from src.llm import DEFAULT_MODEL, ImagePart, LLMError, OpenRouterClient, strict_json_schema
from src.models import ResumeExtraction

KEY = "sk-or-test-SECRET-123"


def client_with(handler, **kw) -> OpenRouterClient:
    return OpenRouterClient(KEY, http=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def ok(content: str):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def call(client):
    return client.complete_json(system="sys", user_text="extract", images=[ImagePart("image/jpeg", b"\xff\xd8abc")],
                                schema_name="resume_extraction", schema={"type": "object"})


def test_request_shape():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        return ok('{"a": 1}')

    assert call(client_with(handler)) == '{"a": 1}'
    body = seen["body"]
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    assert body["model"] == DEFAULT_MODEL == "anthropic/claude-sonnet-4.6"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"] == {"name": "resume_extraction", "strict": True,
                                                      "schema": {"type": "object"}}
    assert body["provider"] == {"require_parameters": True} and body["temperature"] == 0
    user = body["messages"][1]["content"]
    assert user[0] == {"type": "text", "text": "extract"}
    assert user[1]["type"] == "image_url"
    assert user[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_timeout_becomes_llm_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)
    with pytest.raises(LLMError, match="timed out"):
        call(client_with(handler))


def test_rate_limit_becomes_llm_error():
    handler = lambda r: httpx.Response(429, json={"error": {"message": "rate limited"}})  # noqa: E731
    with pytest.raises(LLMError, match="429.*rate limited"):
        call(client_with(handler))


def test_server_error_and_network_error_and_bad_envelopes():
    with pytest.raises(LLMError, match="500"):
        call(client_with(lambda r: httpx.Response(500, text="boom")))

    def refuse(request):
        raise httpx.ConnectError("no route", request=request)
    with pytest.raises(LLMError, match="network error"):
        call(client_with(refuse))
    with pytest.raises(LLMError, match="non-JSON"):
        call(client_with(lambda r: httpx.Response(200, text="<html>")))
    with pytest.raises(LLMError, match="error"):
        call(client_with(lambda r: httpx.Response(200, json={"error": {"message": "upstream failed"}})))
    with pytest.raises(LLMError, match="no choices"):
        call(client_with(lambda r: httpx.Response(200, json={"choices": []})))


def test_empty_content_is_returned_not_raised():
    assert call(client_with(lambda r: ok(""))) == ""   # validation (and retry) is the caller's job


def test_from_env():
    assert OpenRouterClient.from_env({}) is None
    assert OpenRouterClient.from_env({"OPENROUTER_API_KEY": "  "}) is None
    c = OpenRouterClient.from_env({"OPENROUTER_API_KEY": KEY, "OPENROUTER_MODEL": ""})
    assert c.model == DEFAULT_MODEL
    assert OpenRouterClient.from_env({"OPENROUTER_API_KEY": KEY, "OPENROUTER_MODEL": "x/y"}).model == "x/y"


def test_key_is_never_exposed():
    c = client_with(lambda r: httpx.Response(401, json={"error": {"message": "invalid key"}}))
    assert KEY not in repr(c) and KEY not in str(c)
    with pytest.raises(LLMError) as e:
        call(c)
    assert KEY not in str(e.value)


def test_schema_is_generated_from_the_model_and_has_no_decision_fields():
    schema = strict_json_schema(ResumeExtraction)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text and "default" not in schema["properties"]

    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for v in node:
                yield from objects(v)

    for obj in objects(schema):
        assert obj["additionalProperties"] is False and obj["required"] == list(obj["properties"])
    banned = {"eligible", "score", "rank", "penalty", "depth", "recommendation", "strengths", "concerns"}
    assert not banned & set(schema["properties"])
    for word in ("eligib", "score", "shortlist", "rank"):
        assert word not in text.lower(), word   # the model is never even told these concepts
