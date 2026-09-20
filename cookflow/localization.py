"""Reviewed Chinese ingredient labels; retain unmodified source fields separately."""
import re

NAMES = {
    'Basil Leaves': '罗勒叶', 'Brown Sugar': '红糖', 'Canola Oil': '菜籽油',
    'Carrots': '胡萝卜', 'Chicken': '鸡肉', 'Chicken Bouillon Powder': '鸡汤粉',
    'Chicken Stock': '鸡高汤', 'Chicken Thighs': '鸡腿肉', 'Chilli Powder': '辣椒粉',
    'Chinese five spice powder': '五香粉', 'Coriander': '香菜', 'Corn Flour': '玉米淀粉',
    'Cornstarch': '玉米淀粉', 'Cucumber': '黄瓜', 'Doubanjiang': '豆瓣酱',
    'Dry sherry': '干雪利酒', 'Egg': '鸡蛋', 'Eggs': '鸡蛋',
    'Fermented Black Beans': '豆豉', 'Garlic': '大蒜', 'Garlic Clove': '蒜瓣',
    'Ginger': '生姜', 'Ginger Cordial': '姜味甜饮', 'Ground Ginger': '姜粉',
    'Hotsauce': '辣椒酱', 'Jasmine Rice': '茉莉香米', 'Kosher Salt': '粗盐',
    'Minced Beef': '牛肉末', 'Mushrooms': '蘑菇', 'Olive Oil': '橄榄油',
    'Onion': '洋葱', 'Peanut Oil': '花生油', 'Peanuts': '花生', 'Peas': '豌豆',
    'Pepper': '胡椒粉', 'Plum Tomatoes': '长圆番茄', 'Pork': '猪肉',
    'Red Chilli Flakes': '红辣椒碎', 'Rice': '大米', 'Rice Vinegar': '米醋',
    'Sake': '清酒', 'Salt': '盐', 'Scallions': '小葱', 'Sesame Seed': '芝麻',
    'Sesame Seed Oil': '香油', 'Shrimp': '虾仁', 'Sichuan pepper': '花椒',
    'Snow Peas': '荷兰豆', 'Soy Sauce': '酱油', 'Spring Onions': '小葱',
    'Starch': '淀粉', 'Sugar': '白糖', 'Tofu': '豆腐', 'Tomato Puree': '番茄泥',
    'Vegetable Oil': '植物油', 'Vinegar': '醋', 'Water': '水', 'Water Chestnut': '荸荠',
    'Wood Ear Mushrooms': '木耳',
}

# Source ingredient labels conflict with the actual instructions in these records.
CONTEXT_NAMES = {
    ('52956', 'Ginger Cordial'): ('姜汁', '来源步骤明确写作 ginger juice，按做法校正食材标签。'),
    ('53367', 'Ground Ginger'): ('姜末', '来源步骤写作 minced garlic and ginger，按做法译为姜末。'),
}


def chinese_measure(measure, source_name):
    value = ' '.join(measure.strip().lower().split())
    if value in ('dash', 'pinch'):
        return '少许' if value == 'dash' else '一小撮'
    # Preserve original amounts, including fractions; no guessed cup-to-gram conversion.
    value = value.replace('2-1/2', '2又1/2').replace('1-½', '1又1/2')
    value = re.sub(r'(\d+) (\d+/\d+)', r'\1又\2', value)
    quantity_units = ((r'\b(?:tablespoons?|tbsp|tbs)\b', '汤匙'),
                      (r'\btsp\b', '茶匙'), (r'\bcups?\b', '杯'),
                      (r'\blb\b', '磅'), (r'\boz\b', '盎司'),
                      (r'(?<=\d)ml\b', '毫升'), (r'(?<=\d)g\b', '克'),
                      (r'\bcloves?\b', '瓣'))
    for pattern, translated in quantity_units:
        value = re.sub(pattern, translated, value)
    count_unit = {'Spring Onions': '根', 'Scallions': '根', 'Egg': '个', 'Eggs': '个',
                  'Basil Leaves': '片', 'Cucumber': '根', 'Carrots': '根'}.get(source_name, '个')
    value = re.sub(r'\bmedium\b', count_unit + '（中等大小）', value)
    value = re.sub(r'\blarge\b', count_unit + '（大号）', value)
    if 'sliced' in value and source_name == 'Ginger':
        value = value.replace('sliced', '片')
    else:
        value = value.replace('sliced', '（切片）')
    value = value.replace('chopped', '（切碎）').replace('minced', '（切末）')
    value = value.replace(' ', '')
    if re.fullmatch(r'\d+', value):
        value += count_unit
    elif re.fullmatch(r'\d+（切(?:碎|片|末)）', value):
        value = re.sub(r'^(\d+)', r'\1' + count_unit, value)
    if re.search('[A-Za-z]', value):
        raise ValueError(f'Untranslated ingredient measure: {measure}')
    return value


def localize_ingredient(name, measure, meal_id):
    translated = NAMES[name]  # Reject missing seed translations instead of displaying English.
    provenance = {'type': 'translation', 'method': 'reviewed-zh-CN-v1'}
    override = CONTEXT_NAMES.get((meal_id, name))
    if override:
        translated, note = override
        provenance['note'] = note
    amount = chinese_measure(measure, name)
    return {'name': translated, 'measure': amount, 'text': f'{translated} {amount}'.strip(),
            'original_name': name, 'original_measure': measure,
            'original_text': f'{measure} {name}'.strip(), 'language': 'zh-CN',
            'provenance': provenance}
