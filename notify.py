import os
import json
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


def summarize_with_gemini(todos):
    text = '\n'.join(f'- {t["text"]}' for t in todos)
    prompt = (
        '다음은 오늘 처리해야 할 업무 목록입니다. '
        '핵심만 2~3줄로 간결하게 요약해주세요. 한국어로 작성하세요.\n\n'
        f'{text}'
    )
    resp = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_AI_KEY}',
        headers={'Content-Type': 'application/json'},
        json={'contents': [{'parts': [{'text': prompt}]}]}
    )
    data = resp.json()
    if 'candidates' not in data:
        raise Exception(f'Gemini 오류: {data}')
    return data['candidates'][0]['content']['parts'][0]['text']


def send_kakao(access_token, template):
    resp = requests.post(
        'https://kapi.kakao.com/v2/api/talk/memo/default/send',
        headers={'Authorization': f'Bearer {access_token}'},
        data={'template_object': json.dumps(template, ensure_ascii=False)}
    )
    return resp.json()


def build_link(url):
    return {'web_url': url, 'mobile_web_url': url}


def build_completion_url(block_id):
    return f'{WORKER_URL}/done?id={block_id}&secret={CALLBACK_SECRET}'


if __name__ == '__main__':
    print('1. Kakao 액세스 토큰 발급 중...')
    access_token = get_kakao_access_token()
    print('   완료')

    print('2. Notion 미체크 항목 수집 중...')
    todos = collect_unchecked_todos(NOTION_PAGE_ID)
    print(f'   미체크 항목: {len(todos)}개')
    for t in todos:
        print(f'   - {t["text"]}')

    if not todos:
        send_kakao(access_token, {
            'object_type': 'text',
            'text': '📋 오늘의 인수인계\n\n미완료 항목이 없습니다. 수고하셨습니다! 🎉',
            'link': {'web_url': NOTION_PAGE_URL}
        })
        print('   미완료 항목 없음 메시지 전송 완료')
    else:
        print('3. Gemini로 요약 중...')
        summary = summarize_with_gemini(todos)
        print(f'   요약:\n{summary}')

        print('4. 요약 메시지 전송 중...')
        result = send_kakao(access_token, {
            'object_type': 'text',
            'text': f'📋 오늘의 인수인계 요약\n\n{summary}',
            'link': build_link(NOTION_PAGE_URL)
        })
        print(f'   결과: {result}')

        print('5. 미완료 항목 리스트 전송 중...')
        # KakaoTalk list template: 2~5 items required
        display_todos = todos[:5]
        contents = [
            {
                'title': t['text'],
                'description': '탭하면 Notion에서 완료 처리됩니다',
                'link': build_link(build_completion_url(t['id']))
            }
            for t in display_todos
        ]

        # Minimum 2 items required for list template
        if len(contents) == 1:
            contents.append({
                'title': f'총 {len(todos)}개 항목',
                'description': 'Notion에서 전체 확인',
                'link': build_link(NOTION_PAGE_URL)
            })

        remaining = len(todos) - len(display_todos)
        header = f'☐ 미완료 항목 ({len(todos)}개)' if remaining == 0 else f'☐ 미완료 항목 ({len(todos)}개 중 5개 표시)'

        result = send_kakao(access_token, {
            'object_type': 'list',
            'header_title': header,
            'header_link': build_link(NOTION_PAGE_URL),
            'contents': contents,
            'buttons': [{'title': 'Notion 전체보기', 'link': build_link(NOTION_PAGE_URL)}]
        })
        print(f'   결과: {result}')

    print('완료!')
