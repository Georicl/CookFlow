import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .catalog import validate
from .scheduler import schedule

RESOURCES = {'person', 'burner', 'wok', 'pot', 'board', 'oven'}


class ReviewInput(BaseModel):
    base_version: int
    servings: Annotated[int, Field(ge=1, le=30)]
    steps: Annotated[list[dict], Field(min_length=1, max_length=80)]
    resource_holds: list[dict] = Field(default_factory=list, max_length=80)


class PlanInput(BaseModel):
    recipe_ids: Annotated[list[str], Field(min_length=1, max_length=6)]
    resources: dict[str, Annotated[int, Field(ge=0, le=8)]]


class ProgressInput(BaseModel):
    completed: list[str]


def create_app(catalog_path=None, user_path=None, web_path=None):
    catalog = Path(catalog_path or os.getenv('COOKFLOW_CATALOG', 'data/catalog.sqlite')).resolve()
    users = Path(user_path or os.getenv('COOKFLOW_USERS', 'data/user.sqlite')).resolve()
    if catalog == users:
        raise ValueError('User database must be separate from catalog')
    users.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(users)) as con:
        con.executescript('''
            CREATE TABLE IF NOT EXISTS profiles (
                recipe_id TEXT PRIMARY KEY, base_version INTEGER NOT NULL,
                document TEXT NOT NULL, reviewed_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS plans (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                document TEXT NOT NULL, completed TEXT NOT NULL DEFAULT '[]');
        ''')
    app = FastAPI(title='CookFlow', version='0.2.0')

    def catalog_rows():
        if not catalog.exists():
            raise HTTPException(503, '食谱库尚未导入，请运行 uv run cookflow seed')
        with closing(sqlite3.connect(catalog.as_uri() + '?mode=ro', uri=True)) as con:
            return con.execute('SELECT r.id, v.version, v.document FROM recipes r JOIN recipe_versions v ON r.id=v.recipe_id AND r.current_version=v.version ORDER BY r.id').fetchall()

    def documents():
        with closing(sqlite3.connect(users)) as con:
            profiles = {r[0]: (r[1], json.loads(r[2])) for r in con.execute('SELECT recipe_id, base_version, document FROM profiles')}
        result = []
        for rid, version, payload in catalog_rows():
            original = json.loads(payload)
            profile = profiles.get(rid)
            doc = profile[1] if profile and profile[0] == version else original
            result.append({**doc, 'version': version, 'has_profile': bool(profile and profile[0] == version),
                           'profile_outdated': bool(profile and profile[0] != version)})
        return result

    def get_recipe(rid):
        doc = next((d for d in documents() if d['id'] == rid), None)
        if not doc:
            raise HTTPException(404, '找不到这道菜')
        return doc

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'recipes': len(catalog_rows())}

    @app.get('/api/recipes')
    def recipes(q: str = '', category: str = ''):
        docs = documents()
        if q:
            docs = [d for d in docs if q.casefold() in (d['title'] + d.get('original_title', '') + ' '.join(i['text'] for i in d['ingredients'])).casefold()]
        if category:
            docs = [d for d in docs if d.get('category') == category]
        return {'items': docs, 'total': len(docs)}

    @app.get('/api/recipes/{recipe_id:path}')
    def recipe(recipe_id: str):
        return get_recipe(recipe_id)

    @app.post('/api/profiles/{recipe_id:path}')
    def review(recipe_id: str, body: ReviewInput):
        doc = get_recipe(recipe_id)
        if body.base_version != doc['version']:
            raise HTTPException(409, '食谱已更新，请重新打开后确认')
        for step in body.steps:
            resources = step.get('resources', {})
            if not isinstance(resources, dict) or set(resources) - RESOURCES:
                raise HTTPException(422, '未知厨具类型')
            if type(step.get('duration_seconds')) is not int or not 1 <= step['duration_seconds'] <= 86400:
                raise HTTPException(422, '步骤时长须在 1 秒到 24 小时之间')
            step['provenance'] = {key: {'type': 'estimate', 'note': '用户在本地调度编辑器中确认的估计值'}
                                  for key in ('duration_seconds', 'resources', 'depends_on', 'mode')}
        now = datetime.now(timezone.utc).isoformat()
        doc.update(status='ready', servings=body.servings, steps=body.steps, resource_holds=body.resource_holds,
                   review={'by': 'local-user', 'at': now})
        try:
            validate(doc)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        with closing(sqlite3.connect(users)) as con, con:
            con.execute('INSERT INTO profiles VALUES (?, ?, ?, ?) ON CONFLICT(recipe_id) DO UPDATE SET base_version=excluded.base_version, document=excluded.document, reviewed_at=excluded.reviewed_at',
                        (recipe_id, doc['version'], json.dumps(doc, ensure_ascii=False), now))
        return get_recipe(recipe_id)

    @app.post('/api/plans')
    def create_plan(body: PlanInput):
        if len(set(body.recipe_ids)) != len(body.recipe_ids):
            raise HTTPException(422, '菜单不能重复选同一道菜')
        if set(body.resources) - RESOURCES or not body.resources.get('person'):
            raise HTTPException(422, '请配置厨具和至少一位做饭的人')
        docs = [get_recipe(rid) for rid in body.recipe_ids]
        try:
            plan = schedule(docs, body.resources)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        plan.update(id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(), recipes=docs, completed=[])
        with closing(sqlite3.connect(users)) as con, con:
            con.execute('INSERT INTO plans (id, created_at, document) VALUES (?, ?, ?)',
                        (plan['id'], plan['created_at'], json.dumps(plan, ensure_ascii=False)))
        return plan

    def load_plan(plan_id):
        with closing(sqlite3.connect(users)) as con:
            row = con.execute('SELECT document, completed FROM plans WHERE id=?', (plan_id,)).fetchone()
        if not row:
            raise HTTPException(404, '找不到这份安排')
        return {**json.loads(row[0]), 'completed': json.loads(row[1])}

    @app.get('/api/plans')
    def plans():
        with closing(sqlite3.connect(users)) as con:
            rows = con.execute('SELECT id, created_at, document, completed FROM plans ORDER BY created_at DESC LIMIT 20').fetchall()
        return {'items': [{'id': r[0], 'created_at': r[1], 'titles': [d['title'] for d in json.loads(r[2])['recipes']],
                           'duration_seconds': json.loads(r[2])['duration_seconds'], 'completed_count': len(json.loads(r[3]))} for r in rows]}

    @app.get('/api/plans/{plan_id}')
    def plan(plan_id: str):
        return load_plan(plan_id)

    @app.patch('/api/plans/{plan_id}/progress')
    def progress(plan_id: str, body: ProgressInput):
        plan = load_plan(plan_id)
        known = {t['id'] for t in plan['tasks']}
        if set(body.completed) - known or len(body.completed) != len(set(body.completed)):
            raise HTTPException(422, '无效步骤')
        for task in plan['tasks']:
            if task['id'] in body.completed and not set(task['depends_on']) <= set(body.completed):
                raise HTTPException(422, '请先完成前置步骤')
        with closing(sqlite3.connect(users)) as con, con:
            con.execute('UPDATE plans SET completed=? WHERE id=?', (json.dumps(body.completed), plan_id))
        return load_plan(plan_id)

    # Never serve data/, raw responses, or the project directory as static assets.
    static = Path(web_path or Path(__file__).resolve().parents[1] / 'web/dist')
    if static.is_dir():
        app.mount('/', StaticFiles(directory=static, html=True), name='web')
    return app
