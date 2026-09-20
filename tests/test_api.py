import copy
import hashlib
import json
from pathlib import Path
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from cookflow.api import create_app
from cookflow.catalog import connect, ingest
from cookflow.scheduler import fits, schedule


def example():
    return json.loads((Path(__file__).resolve().parents[1] / 'recipes/zh-CN/tomato-egg.json').read_text())


@pytest.fixture
def kitchen(tmp_path):
    catalog = tmp_path / 'catalog.sqlite'
    with closing(connect(catalog)) as con:
        ingest(con, example())
    client = TestClient(create_app(catalog, tmp_path / 'users.sqlite', tmp_path / 'no-web'))
    return client, catalog


def review_payload(doc):
    return {'base_version': 1, 'servings': 2, 'steps': doc['steps'], 'resource_holds': doc['resource_holds']}


def test_complete_api_flow_does_not_write_catalog(kitchen):
    client, catalog = kitchen
    before = hashlib.sha256(catalog.read_bytes()).hexdigest()
    rid = example()['id']
    assert client.get('/api/recipes', params={'q': '番茄'}).json()['total'] == 1
    request = {'recipe_ids': [rid], 'resources': {'person': 1, 'burner': 1, 'board': 1, 'wok': 1}}
    assert client.post('/api/plans', json=request).status_code == 422
    assert client.post('/api/profiles/' + rid, json=review_payload(example())).status_code == 200
    result = client.post('/api/plans', json=request)
    assert result.status_code == 200, result.text
    plan = result.json()
    assert len(plan['tasks']) == 4
    assert plan['duration_seconds'] == 660
    progress = '/api/plans/' + plan['id'] + '/progress'
    assert client.patch(progress, json={'completed': [plan['tasks'][-1]['id']]}).status_code == 422
    assert client.patch(progress, json={'completed': [plan['tasks'][0]['id']]}).status_code == 200
    assert client.get('/api/plans/' + plan['id']).json()['completed'] == [plan['tasks'][0]['id']]
    assert len(client.get('/api/plans').json()['items']) == 1
    assert hashlib.sha256(catalog.read_bytes()).hexdigest() == before


def test_stale_review_and_insufficient_resources(kitchen):
    client, catalog = kitchen
    body = review_payload(example())
    body['base_version'] = 9
    assert client.post('/api/profiles/' + example()['id'], json=body).status_code == 409
    body['base_version'] = 1
    assert client.post('/api/profiles/' + example()['id'], json=body).status_code == 200
    assert client.post('/api/plans', json={'recipe_ids': [example()['id']], 'resources': {'person': 1}}).status_code == 422
    newer = example()
    newer['title'] = '更新的食谱'
    with closing(connect(catalog)) as con:
        ingest(con, newer)
    doc = client.get('/api/recipes/' + newer['id']).json()
    assert doc['profile_outdated'] and doc['status'] == 'draft'


def ready(doc):
    doc = copy.deepcopy(doc)
    doc.update(status='ready', review={'by': 'test', 'at': '2026-09-21'})
    return doc


def test_schedule_respects_capacity_and_holds():
    first = ready(example())
    second = copy.deepcopy(first)
    second['id'] = 'second'
    capacity = {'person': 2, 'board': 2, 'burner': 2, 'wok': 1}
    result = schedule([first, second], capacity)
    assert fits(result['tasks'], [], capacity)
    cooking = [t for t in result['tasks'] if t['resources'].get('wok')]
    first_end = max(t['end'] for t in cooking if t['recipe_id'] == first['id'])
    second_start = min(t['start'] for t in cooking if t['recipe_id'] == 'second')
    assert second_start >= first_end


def test_passive_time_allows_another_recipe():
    first = ready(example())
    first['resource_holds'] = []
    first['steps'] = [first['steps'][0]]
    first['steps'][0].update(duration_seconds=600, mode='passive', resources={'pot': 1})
    second = ready(example())
    result = schedule([first, {**second, 'id': 'second'}], {'person': 1, 'board': 1, 'burner': 1, 'wok': 1, 'pot': 1})
    assert result['duration_seconds'] < result['sequential_seconds']


def test_all_ten_imports_and_available_raw_sources():
    from cookflow.importer import SEEDS, normalize
    from cookflow.catalog import validate
    root = Path(__file__).resolve().parents[1]
    for meal_id in SEEDS:
        path = root / 'recipes/imported' / f'{meal_id}.json'
        doc = json.loads(path.read_text())
        validate(doc)
        assert len(doc['ingredients']) > 0 and len(doc['steps']) > 0
        assert doc['status'] == 'draft'
        raw = root / 'data/raw/themealdb' / f'{meal_id}.json'
        if not raw.exists():
            continue  # Raw acquisition cache remains on the author's laptop.
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == doc['source']['raw_sha256']
        assert normalize(json.loads(raw.read_bytes())['meals'][0], raw.read_bytes(), doc['source']['retrieved_at']) == doc
