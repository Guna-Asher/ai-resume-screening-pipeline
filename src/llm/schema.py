"""Generate a strict-mode JSON Schema from a Pydantic model (single source of truth)."""
from pydantic import BaseModel

_DROP = {"default", "title"}


def strict_json_schema(model: type[BaseModel]) -> dict:
    """Inline $refs, forbid extra keys and mark every property required.

    Strict structured-output modes require this shape; optional values stay expressible as
    nullable types / empty lists, and the Pydantic defaults still apply when we validate.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    schema.pop("description", None)  # the class docstring is for engineers, not for the model

    def walk(node):
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            resolved = walk(defs[node["$ref"].split("/")[-1]])
            resolved.update(walk({k: v for k, v in node.items() if k != "$ref"}))
            return resolved
        out = {}
        for key, value in node.items():
            if key == "properties":
                out[key] = {name: walk(sub) for name, sub in value.items()}
            elif key not in _DROP:
                out[key] = walk(value)
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out

    return walk(schema)
