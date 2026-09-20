"""Fetch a small, reproducible seed catalog via TheMealDB's official API."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .catalog import connect, ingest
from .localization import localize_ingredient

SEEDS = {
    '53372': '番茄炒蛋', '52947': '麻婆豆腐', '52945': '宫保鸡丁',
    '52955': '蛋花汤', '52954': '酸辣汤', '52956': '鸡肉粥',
    '53367': '鸡肉炒饭', '53378': '芝麻黄瓜沙拉',
    '53375': '荷兰豆炒虾仁', '52949': '糖醋猪肉',
}
BASE = 'https://www.themealdb.com/api/json/v1/1/'


def normalize(meal, raw, retrieved_at):
    meal_id = meal['idMeal']
    instructions = meal.get('strInstructions', '').strip()
    # Curated notes offsets for this ten-recipe seed set, checked against the raw API.
    # Keep original wording. A paragraph may contain several actions; review can split it.
    paragraphs = [s.strip() for s in re.split(r'\r?\n+', instructions) if s.strip()]
    paragraphs = [s for s in paragraphs if not re.fullmatch(r'(?:STEP\s*)?\d+[.:]?', s, re.I)]
    notes_count = {'53372': 1, '53375': 1, '53367': 3}.get(meal_id, 0)
    notes, paragraphs = paragraphs[:notes_count], paragraphs[notes_count:]
    cleaned, heading = [], ''
    for paragraph in paragraphs:
        if paragraph == meal['strMeal']:
            continue
        if re.match(r'^STEP\s+\d+\s*[-:]', paragraph, re.I) or paragraph.endswith(':') or paragraph in ('Preparation', 'Cooking Instructions'):
            heading = paragraph
            continue
        cleaned.append((heading + '\n' + paragraph).strip())
        heading = ''
    paragraphs = cleaned
    if not paragraphs:
        raise ValueError(f'{meal_id}: no instructions')
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f'strIngredient{i}') or '').strip()
        measure = (meal.get(f'strMeasure{i}') or '').strip()
        if name:
            ingredients.append(localize_ingredient(name, measure, meal_id))
    return {
        'schema_version': 1, 'id': f'themealdb/{meal_id}',
        'title': SEEDS.get(meal_id, meal['strMeal']), 'original_title': meal['strMeal'],
        'language': 'en', 'ingredient_language': 'zh-CN', 'servings': 2, 'servings_note': '源数据未提供份数；2 为待确认的界面初始值。',
        'status': 'draft', 'category': meal.get('strCategory'), 'area': meal.get('strArea'),
        'image_url': meal.get('strMealThumb'),
        'source': {'kind': 'api', 'name': 'TheMealDB',
                   'attribution': 'Recipe and artwork: TheMealDB; Chinese display title: CookFlow',
                   'license': 'TheMealDB Terms of Use',
                   'license_url': 'https://www.themealdb.com/terms_of_use.php',
                   'url': f'https://www.themealdb.com/meal/{meal_id}',
                   'upstream_url': meal.get('strSource') or None,
                   'api_url': BASE + f'lookup.php?i={meal_id}',
                   'retrieved_at': retrieved_at, 'raw_sha256': hashlib.sha256(raw).hexdigest()},
        'ingredients': ingredients,
        'notes': notes,
        'steps': [{'id': f's{i+1}', 'instruction': p, 'depends_on': [f's{i}'] if i else []}
                  for i, p in enumerate(paragraphs)],
        'resource_holds': [],
    }


def seed(database='data/catalog.sqlite', refresh=False):
    raw_dir, normalized_dir = Path('data/raw/themealdb'), Path('recipes/imported')
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    results = []
    con = connect(database)
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            for meal_id in SEEDS:
                path = raw_dir / f'{meal_id}.json'
                stamp = raw_dir / f'{meal_id}.meta.json'
                if refresh or not path.exists():
                    response = client.get(BASE + 'lookup.php', params={'i': meal_id})
                    response.raise_for_status()
                    raw = response.content
                    meals = response.json().get('meals')
                    if not meals or meals[0]['idMeal'] != meal_id:
                        raise ValueError(f'Invalid API response for {meal_id}')
                    if not path.exists() or raw != path.read_bytes():
                        path.write_bytes(raw)
                        stamp.write_text(json.dumps({'retrieved_at': datetime.now(timezone.utc).isoformat()}))
                raw = path.read_bytes()
                doc = normalize(json.loads(raw)['meals'][0], raw, json.loads(stamp.read_text())['retrieved_at'])
                result = ingest(con, doc)
                (normalized_dir / f'{meal_id}.json').write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
                results.append({**result, 'title': doc['title'], 'steps': len(doc['steps'])})
    finally:
        con.close()
    return results
