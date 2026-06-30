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
    resp = requests.get(
        f'https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children',
        headers=NOTION_HEADERS,
        params={'page_size': 100}
    )
    return resp.json().get('results', [])


def collect_unchecked_todos(blocks):
    todos = []
    for block in blocks:
        if block.get('type') == 'to_do':
            td = block.get('to_do', {})
            if not td.get('checked', False):
                text = ''.join(rt.get('plain_text', '') for rt in td.get('rich_text', []))
                if text:
                    todos.append({'id': block['id'], 'text': text})
    return todos


def sort_unchecked_to_bottom(blocks):
    todos = [b for b in blocks if b.get('type') == 'to_do']
    unchecked = [b for b in todos if not b['to_do'].get('checked', False)]

    if not unchecked:
        print('   모든 항목 완료 — 정렬 불필요')
        return

    checked_indices = [i for i, b in enumerate(todos) if b['to_do'].get('checked', False)]
    unchecked_indices = [i for i, b in enumerate(todos) if not b['to_do'].get('checked', False)]

    last_checked = max(checked_indices, default=-1)
    first_unchecked = min(unchecked_indices, default=0)

    if first_unchecked > last_checked:
        print('   이미 올바르게 정렬됨 — 스킵')
        return

    print(f'   미완료 항목 {len(unchecked)}개 아래로 이동 중...')
    for block in unchecked:
        rich_text = block['to_do'].get('rich_text', [])
        requests.delete(
            f'https://api.notion.com/v1/blocks/{block["id"]}',
            headers=NOTION_HEADERS
        )
        requests.patch(
            f'https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children',
            headers={**NOTION_HEADERS, 'Content-Type': 'application/json'},
            json={'children': [{'type': 'to_do', 'to_do': {'rich_text': rich_text, 'checked': False}}]}
        )
    print('   정렬 완료')


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

    print('2. Notion 블록 가져오기...')
    blocks = get_page_blocks()

    print('3. 미완료 항목 수집 중...')
    todos = collect_unchecked_todos(blocks)
    print(f'   미완료 항목: {len(todos)}개')

    print('4. 카카오톡 전송 중...')
    if not todos:
        send_kakao(access_token, {
            'object_type': 'text',
            'text': '📋 오늘의 할 일\n\n🎉 모든 할 일을 완료했어요!',
            'link': build_link(NOTION_PAGE_URL)
        })
        print('   미완료 항목 없음 — 완료 메시지 전송')
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

        header = f'📋 TO-DO LIST  ·  미완료 {len(todos)}개'
        result = send_kakao(access_token, {
            'object_type': 'list',
            'header_title': header,
            'header_link': build_link(NOTION_PAGE_URL),
            'contents': contents,
            'buttons': [{'title': f'Notion 전체보기', 'link': build_link(NOTION_PAGE_URL)}]
        })
        print(f'   전송 결과: {result}')

    print('5. Notion 미완료 항목 아래로 정렬 중...')
    sort_unchecked_to_bottom(blocks)

    print('완료!')
