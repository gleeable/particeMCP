import os
import json
import urllib.parse
import requests

NOTION_API_KEY = os.environ['NOTION_API_KEY']
NOTION_PAGE_ID = '30bb8f52b84f80999186e42ccce1968f'
KAKAO_REST_API_KEY = os.environ['KAKAO_REST_API_KEY']
KAKAO_REFRESH_TOKEN = os.environ['KAKAO_REFRESH_TOKEN']
KAKAO_CLIENT_SECRET = os.environ['KAKAO_CLIENT_SECRET']
WORKER_URL = os.environ['CLOUDFLARE_WORKER_URL'].rstrip('/')
CALLBACK_SECRET = os.environ['CALLBACK_SECRET']

NOTION_PAGE_URL = 'https://www.notion.so/TO-DO-LIST-30bb8f52b84f80999186e42ccce1968f'
NOTION_HEADERS = {
    'Authorization': f'Bearer {NOTION_API_KEY}',
    'Notion-Version': '2022-06-28',
}


def get_kakao_access_token():
    resp = requests.post('https://kauth.kakao.com/oauth/token', data={
        'grant_type': 'refresh_token',
        'client_id': KAKAO_REST_API_KEY,
        'client_secret': KAKAO_CLIENT_SECRET,
        'refresh_token': KAKAO_REFRESH_TOKEN,
    })
    data = resp.json()
    if 'access_token' not in data:
        raise Exception(f'토큰 발급 실패: {data}')
    return data['access_token']


def get_page_blocks():
    """페이지네이션으로 최상위 블록 전부 수집"""
    blocks = []
    cursor = None
    while True:
        params = {'page_size': 100}
        if cursor:
            params['start_cursor'] = cursor
        resp = requests.get(
            f'https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children',
            headers=NOTION_HEADERS,
            params=params
        )
        data = resp.json()
        blocks.extend(data.get('results', []))
        if not data.get('has_more'):
            break
        cursor = data.get('next_cursor')
    return blocks


def sort_unchecked_to_bottom(top_blocks):
    """미완료 항목을 맨 아래로 이동. 재생성된 블록의 새 ID를 반환."""
    todos = [b for b in top_blocks if b.get('type') == 'to_do']
    unchecked = [b for b in todos if not b['to_do'].get('checked', False)]

    if not unchecked:
        print('   모든 항목 완료 — 정렬 불필요')
        return {}

    checked_indices = [i for i, b in enumerate(todos) if b['to_do'].get('checked', False)]
    unchecked_indices = [i for i, b in enumerate(todos) if not b['to_do'].get('checked', False)]
    last_checked = max(checked_indices, default=-1)
    first_unchecked = min(unchecked_indices, default=0)

    if first_unchecked > last_checked:
        print('   이미 올바르게 정렬됨 — 스킵')
        return {}  # ID 변경 없음

    print(f'   미완료 항목 {len(unchecked)}개 아래로 이동 중...')
    old_to_new = {}  # {구 ID: 새 ID}

    for block in unchecked:
        rich_text = block['to_do'].get('rich_text', [])
        old_id = block['id']

        requests.delete(
            f'https://api.notion.com/v1/blocks/{old_id}',
            headers=NOTION_HEADERS
        )
        resp = requests.patch(
            f'https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children',
            headers={**NOTION_HEADERS, 'Content-Type': 'application/json'},
            json={'children': [{'type': 'to_do', 'to_do': {'rich_text': rich_text, 'checked': False}}]}
        )
        new_blocks = resp.json().get('results', [])
        if new_blocks:
            old_to_new[old_id] = new_blocks[0]['id']

    print(f'   정렬 완료 (ID {len(old_to_new)}개 갱신)')
    return old_to_new


def collect_unchecked_todos(block_id, depth=0):
    """재귀적으로 미완료 체크박스 수집 (중첩 블록 포함)"""
    if depth > 3:
        return []
    resp = requests.get(
        f'https://api.notion.com/v1/blocks/{block_id}/children',
        headers=NOTION_HEADERS,
        params={'page_size': 100}
    )
    todos = []
    for block in resp.json().get('results', []):
        if block.get('type') == 'to_do':
            td = block.get('to_do', {})
            if not td.get('checked', False):
                text = ''.join(rt.get('plain_text', '') for rt in td.get('rich_text', []))
                if text.strip():
                    todos.append({'id': block['id'], 'text': text.strip()})
        if block.get('has_children'):
            todos.extend(collect_unchecked_todos(block['id'], depth + 1))
    return todos


def build_link(url):
    return {'web_url': url, 'mobile_web_url': url}


def build_completion_url(block_id, text):
    encoded_text = urllib.parse.quote(text[:50])
    return f'{WORKER_URL}/done?id={block_id}&text={encoded_text}&secret={CALLBACK_SECRET}'


def send_kakao(access_token, template):
    resp = requests.post(
        'https://kapi.kakao.com/v2/api/talk/memo/default/send',
        headers={'Authorization': f'Bearer {access_token}'},
        data={'template_object': json.dumps(template, ensure_ascii=False)}
    )
    return resp.json()


if __name__ == '__main__':
    print('1. Kakao 액세스 토큰 발급 중...')
    access_token = get_kakao_access_token()
    print('   완료')

    print('2. Notion 최상위 블록 가져오기...')
    top_blocks = get_page_blocks()
    print(f'   최상위 블록: {len(top_blocks)}개')

    # 정렬을 먼저 → 새 ID 확보 후 메시지 발송
    print('3. 미완료 항목 아래로 정렬 중...')
    sort_unchecked_to_bottom(top_blocks)

    print('4. 정렬 후 미완료 체크박스 수집 (새 ID 기준)...')
    todos = collect_unchecked_todos(NOTION_PAGE_ID)
    print(f'   미완료 항목: {len(todos)}개')

    print('5. 카카오톡 전송 중...')
    if not todos:
        result = send_kakao(access_token, {
            'object_type': 'text',
            'text': '📋 TO-DO LIST\n\n🎉 모든 할 일을 완료했어요!',
            'link': build_link(NOTION_PAGE_URL)
        })
        print(f'   완료 메시지 전송: {result}')
    else:
        display = todos[:5]
        contents = []
        for i, t in enumerate(display, 1):
            contents.append({
                'title': f'{i}.  ☐  {t["text"][:40]}',
                'description': '탭하면 완료 처리됩니다',
                'link': build_link(build_completion_url(t['id'], t['text']))
            })

        if len(contents) == 1:
            contents.append({
                'title': 'Notion에서 전체 보기',
                'description': f'총 {len(todos)}개 항목',
                'link': build_link(NOTION_PAGE_URL)
            })

        result = send_kakao(access_token, {
            'object_type': 'list',
            'header_title': f'📋 TO-DO LIST  ·  미완료 {len(todos)}개',
            'header_link': build_link(NOTION_PAGE_URL),
            'contents': contents,
            'buttons': [{'title': 'Notion 전체보기', 'link': build_link(NOTION_PAGE_URL)}]
        })
        print(f'   전송 결과: {result}')

    print('완료!')
