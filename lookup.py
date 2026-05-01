import json
for item in json.load(open('osrs_mapping.json')):
    name = item.get('name', '').lower()
    if 'masori' in name or 'macuahuitl' in name or ('moon' in name and 'set' in name) or 'virtus' in name or 'justiciar' in name:
        print(f"{item.get('name')}: {item.get('id')} - Limit: {item.get('limit')}")
