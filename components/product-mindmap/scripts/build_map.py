#!/usr/bin/env python3
"""Validate PM mind-map data and inject the unique local template."""
import argparse
import html
import json
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ID = re.compile(r'^[a-zA-Z][a-zA-Z0-9-]*$')

def validate(data):
    if data.get('schema') != 'interactive-mindmap/v1':
        raise ValueError('invalid schema')
    if not ID.fullmatch(data.get('rootId', '')):
        raise ValueError('invalid rootId')
    for field in ('edition', 'kind'):
        if not isinstance(data.get(field), str) or len(data[field]) > 50:
            raise ValueError('invalid ' + field)
    seen = set()
    def visit(item, depth=0):
        if depth > 10 or not isinstance(item, dict):
            raise ValueError('invalid node or excessive depth')
        key = item.get('id', '')
        if not isinstance(key, str) or not ID.fullmatch(key) or key in seen:
            raise ValueError('duplicate or invalid node id')
        seen.add(key)
        if item.get('status') not in ('confirmed', 'suggested', 'pending'):
            raise ValueError('explicit node status required')
        if not isinstance(item.get('title'), str) or not 1 <= len(item['title']) <= 30:
            raise ValueError('node title must be 1-30 characters')
        if not isinstance(item.get('facts'), list) or not all(isinstance(f, list) and len(f) == 2 and all(isinstance(s, str) for s in f) for f in item['facts']):
            raise ValueError('facts must contain label/text pairs')
        if not isinstance(item.get('children'), list):
            raise ValueError('children must be an array')
        if 'caption' in item and (not isinstance(item['caption'], str) or len(item['caption']) > 40):
            raise ValueError('invalid caption')
        if 'side' in item and (depth != 1 or item['side'] not in ('left', 'right')):
            raise ValueError('side is only valid on a main branch')
        for child in item['children']:
            visit(child, depth + 1)
    tree = data.get('root', {})
    if tree.get('id') != 'root' or not 1 <= len(tree.get('children', [])) <= 8:
        raise ValueError('root requires id=root and 1-8 main branches')
    visit(tree)
    if len(seen) > 200:
        raise ValueError('use smaller maps or split this topic')
    if data.get('initialSelected') not in seen or not isinstance(data.get('initialExpanded'), list) or any(i not in seen for i in data['initialExpanded']):
        raise ValueError('initial state references unknown nodes')
    return len(seen)

def build(data, standalone=False):
    validate(data)
    text = (SKILL / 'assets/mindmap.html').read_text(encoding='utf-8')
    values = {'__MAP_ROOT_ID__': data['rootId'], '__MAP_TITLE__': html.escape(data['root']['title']), '__MAP_EDITION__': html.escape(data['edition']), '__MAP_KIND__': html.escape(data['kind'])}
    for key, value in values.items():
        text = text.replace(key, value)
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    text = text.replace('__MINDMAP_DATA__', encoded)
    if '__MAP_' in text or '__MINDMAP_' in text:
        raise ValueError('unresolved template token')
    if standalone:
        shell = (SKILL / 'assets/standalone.html').read_text(encoding='utf-8')
        text = shell.replace('__DOCUMENT_TITLE__', html.escape(data['root']['title'])).replace('__CONTENT__', text)
    return text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--standalone', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    count = validate(data)
    text = build(data, args.standalone)
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding='utf-8') != text:
            raise SystemExit('output differs from current template/data')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(json.dumps({'nodes': count, 'output': str(args.output.resolve()), 'check': args.check}, ensure_ascii=False))

if __name__ == '__main__':
    main()
