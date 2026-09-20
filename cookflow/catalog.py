import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES ('schema_version', '1');
CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY,
    current_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_versions (
    recipe_id TEXT NOT NULL REFERENCES recipes(id),
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    document TEXT NOT NULL,
    PRIMARY KEY (recipe_id, version),
    UNIQUE (recipe_id, content_hash)
);
"""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate(doc):
    """Validate recipe documents; scheduling readiness is explicitly reviewed."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def positive(value):
        return type(value) is int and value > 0

    require(isinstance(doc, dict), "recipe must be an object")
    require(doc.get("schema_version") == 1, "unsupported schema_version")
    for key in ("id", "title", "language"):
        require(text(doc.get(key)), f"missing {key}")
    require(positive(doc.get("servings")), "servings must be a positive integer")
    require(doc.get("status") in ("draft", "ready"), "status must be draft or ready")
    source = doc.get("source")
    require(isinstance(source, dict), "source must be an object")
    for key in ("kind", "name", "attribution", "license"):
        require(text(source.get(key)), f"missing source.{key}")
    require(source["kind"] in ("original", "url", "api", "dataset"), "invalid source kind")
    if source["kind"] != "original":
        for key in ("url", "retrieved_at", "raw_sha256"):
            require(text(source.get(key)), f"missing source.{key}")
        raw_hash = source["raw_sha256"]
        require(len(raw_hash) == 64 and all(c in "0123456789abcdef" for c in raw_hash), "invalid raw_sha256")
    ingredients = doc.get("ingredients")
    require(isinstance(ingredients, list) and bool(ingredients), "ingredients required")
    for item in ingredients:
        require(isinstance(item, dict) and text(item.get("text")), "ingredient requires original text")
    steps = doc.get("steps")
    require(isinstance(steps, list) and bool(steps), "steps required")
    ids = set()
    for step in steps:
        require(isinstance(step, dict), "step must be an object")
        require(text(step.get("id")) and step["id"] not in ids, "step ids must be unique")
        ids.add(step["id"])
        require(text(step.get("instruction")), "step instruction required")
        require(isinstance(step.get("depends_on"), list), "depends_on must be a list")
        require(all(text(d) for d in step["depends_on"]), "dependency ids must be strings")
        if doc["status"] == "ready":
            require(positive(step.get("duration_seconds")), "ready step needs duration_seconds")
            require(step.get("mode") in ("active", "passive"), "ready step needs active/passive mode")
            resources = step.get("resources")
            require(isinstance(resources, dict), "ready step needs explicit resources")
            require(all(text(k) and positive(v) for k, v in resources.items()), "invalid resource quantity")
            if step["mode"] == "active":
                require(resources.get("person", 0) >= 1, "active step must reserve a person")
            provenance = step.get("provenance")
            require(isinstance(provenance, dict), "ready step requires provenance")
            for field in ("duration_seconds", "resources", "depends_on", "mode"):
                evidence = provenance.get(field)
                require(isinstance(evidence, dict), f"missing provenance for {field}")
                require(evidence.get("type") in ("source", "estimate", "measured"), "invalid evidence type")
                require(text(evidence.get("note")), "evidence needs a note")
    graph = {s["id"]: s["depends_on"] for s in steps}
    for dependencies in graph.values():
        require(all(d in ids for d in dependencies), "unknown step dependency")
    remaining = set(ids)
    while remaining:
        available = {s for s in remaining if not (set(graph[s]) & remaining)}
        require(bool(available), "step dependencies contain a cycle")
        remaining -= available
    holds = doc.get("resource_holds", [])
    require(isinstance(holds, list), "resource_holds must be a list")
    for hold in holds:
        require(isinstance(hold, dict), "resource hold must be an object")
        start, end = hold.get("from_step"), hold.get("through_step")
        require(text(start) and text(end) and start in ids and end in ids, "invalid hold endpoints")
        require(text(hold.get("resource")) and positive(hold.get("quantity")), "invalid hold resource")
        ancestors, pending = set(), [end]
        while pending:
            current = pending.pop()
            if current not in ancestors:
                ancestors.add(current)
                pending.extend(graph[current])
        require(start in ancestors, "hold end must depend on its start")
    if doc["status"] == "ready":
        review = doc.get("review")
        require(isinstance(review, dict) and text(review.get("by")) and text(review.get("at")), "ready recipe needs review")
    return doc


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    if con.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] != "1":
        con.close()
        raise ValueError("unsupported database schema")
    return con


def ingest(con, doc):
    validate(doc)
    payload = canonical(doc)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    recipe_id = doc["id"]
    with con:
        existing = con.execute("SELECT version FROM recipe_versions WHERE recipe_id=? AND content_hash=?", (recipe_id, digest)).fetchone()
        if existing:
            return {"id": recipe_id, "version": existing[0], "changed": False}
        version = con.execute("SELECT COALESCE(MAX(version), 0)+1 FROM recipe_versions WHERE recipe_id=?", (recipe_id,)).fetchone()[0]
        con.execute("INSERT INTO recipes VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET current_version=excluded.current_version", (recipe_id, version))
        con.execute("INSERT INTO recipe_versions VALUES (?, ?, ?, ?, ?)", (recipe_id, version, digest, datetime.now(timezone.utc).isoformat(), payload))
    return {"id": recipe_id, "version": version, "changed": True}


def publish(con, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    database = destination / "catalog.sqlite"
    with sqlite3.connect(database) as output:
        con.backup(output)
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "recipes": con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0],
        "versions": con.execute("SELECT COUNT(*) FROM recipe_versions").fetchone()[0],
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    verify(destination)
    return manifest


def verify(destination):
    destination = Path(destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    database = destination / "catalog.sqlite"
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported release schema")
    if hashlib.sha256(database.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("release checksum mismatch")
    con = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or con.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("database integrity check failed")
        if con.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone() != ("1",):
            raise ValueError("unsupported database schema")
        for table, key in (("recipes", "recipes"), ("recipe_versions", "versions")):
            if con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] != manifest[key]:
                raise ValueError("release count mismatch")
        for recipe_id, digest, payload in con.execute("SELECT recipe_id, content_hash, document FROM recipe_versions"):
            doc = validate(json.loads(payload))
            if doc["id"] != recipe_id or hashlib.sha256(canonical(doc).encode()).hexdigest() != digest:
                raise ValueError("recipe content mismatch")
        missing = con.execute("SELECT r.id FROM recipes r LEFT JOIN recipe_versions v ON r.id=v.recipe_id AND r.current_version=v.version WHERE v.recipe_id IS NULL").fetchall()
        if missing:
            raise ValueError("missing current recipe version")
    finally:
        con.close()
    return manifest
