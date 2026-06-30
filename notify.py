import os
import json
import urllib.parse
import requests

NOTION_API_KEY = os.environ['NOTION_API_KEY']
NOTION_PAGE_ID = '30bb8f52b84f80999186e42ccce1968f'
KAKAO_REST_API_KEY = os.environ['KAKAO_REST_API_KEY']
KAKAO_REFRESH_TOKEN = os.environ['KAKAO_REFRESH_TOKEN']
KAKAO_CLIENT_SECRET = os.environ['KAKAO_CLIENT_SECRET']
GOOGLE_AI_KEY = os.environ['GOOGLE_AI_STUDIO']
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


def collect_unchecked_todos(block_id, depth=0):
    if depth > 3:
        return []
    resp = requests.get(
        f'https://api.notion.com/v1/blocks/{block_id}/children',
        headers=NOTION_HEADERS,
        params={'page_size': 100}
    )
    todos = []
    for block in resp.json().get('results', []):
        block_type = block.get('type', '')
        if block_type == 'to_do':
            type_data = block.get('to_do', {})
            if not type_data.get('checked', False):
                text = ''.join(rt.get('plain_text', '') for rt in type_data.get('rich_text', []))
                if text:
                    todos.append({'id': block['id'], 'text': text})
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

    print('2. Notion 미체크 항목 수집 중...')
    todos = collect_unchecked_todos(NOTION_PAGE_ID)
    print(f'   미체크 항목: {len(todos)}개')

    if not todos:
        send_kakao(access_token, {
            'object_type': 'text',
            'text': '📋 오늘의 인수인계\n\n미완료 항목이 없습니다. 수고하셨습니다! 🎉',
            'link': build_link(NOTION_PAGE_URL)
        })
        print('   미완료 항목 없음')
    else:
        # 리스트 템플릿: 항목마다 탭 가능, 탭 시 Notion 체크
        display = todos[:5]
        contents = []
        for i, t in enumerate(display, 1):
            contents.append({
                'title': f'{i}. ☐  {t["text"][:40]}',
                'description': '탭하면 완료 처리됩니다',
                'link': build_link(build_completion_url(t['id'], t['text']))
            })

        # 리스트 템플릿 최소 2개 필요
        if len(contents) == 1:
            contents.append({
                'title': 'Notion에서 전체 보기',
                'description': f'총 {len(todos)}개 항목',
                'link': build_link(NOTION_PAGE_URL)
            })

        remaining = len(todos) - len(display)
        header = f'📋 인수인계 미완료 ({len(todos)}개)'
        if remaining > 0:
            header += f' — 상위 5개 표시'

        result = send_kakao(access_token, {
            'object_type': 'list',
            'header_title': header,
            'header_link': build_link(NOTION_PAGE_URL),
            'contents': contents,
            'buttons': [{'title': f'Notion 전체보기 ({len(todos)}개)', 'link': build_link(NOTION_PAGE_URL)}]
        })
        print(f'   전송 결과: {result}')

    print('완료!')
