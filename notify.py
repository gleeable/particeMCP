import os
import json
import requests

NOTION_API_KEY = os.environ['NOTION_API_KEY']
NOTION_PAGE_ID = '30bb8f52b84f80999186e42ccce1968f'
KAKAO_REST_API_KEY = os.environ['KAKAO_REST_API_KEY']
KAKAO_REFRESH_TOKEN = os.environ['KAKAO_REFRESH_TOKEN']
KAKAO_CLIENT_SECRET = os.environ['KAKAO_CLIENT_SECRET']
GOOGLE_AI_KEY = os.environ['GOOGLE_AI_STUDIO']


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


def get_notion_blocks(block_id, headers):
    resp = requests.get(
        f'https://api.notion.com/v1/blocks/{block_id}/children',
        headers=headers,
        params={'page_size': 100}
    )
    return resp.json().get('results', [])


def extract_text(blocks, headers, depth=0):
    lines = []
    for block in blocks:
        block_type = block.get('type', '')
        type_data = block.get(block_type, {})
        rich_text = type_data.get('rich_text', [])
        text = ''.join(rt.get('plain_text', '') for rt in rich_text)

        if block_type == 'heading_1' and text:
            lines.append(f'\n# {text}')
        elif block_type == 'heading_2' and text:
            lines.append(f'\n## {text}')
        elif block_type == 'heading_3' and text:
            lines.append(f'\n### {text}')
        elif block_type == 'bulleted_list_item' and text:
            indent = '  ' * depth
            lines.append(f'{indent}• {text}')
        elif block_type == 'numbered_list_item' and text:
            indent = '  ' * depth
            lines.append(f'{indent}- {text}')
        elif block_type == 'to_do' and text:
            checked = '✅' if type_data.get('checked') else '☐'
            lines.append(f'{checked} {text}')
        elif block_type == 'paragraph' and text:
            lines.append(text)
        elif block_type == 'callout' and text:
            lines.append(f'[{text}]')

        if block.get('has_children') and depth < 2:
            child_blocks = get_notion_blocks(block['id'], headers)
            lines.extend(extract_text(child_blocks, headers, depth + 1))

    return lines


def get_notion_content():
    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Notion-Version': '2022-06-28',
    }
    blocks = get_notion_blocks(NOTION_PAGE_ID, headers)
    lines = extract_text(blocks, headers)
    return '\n'.join(lines).strip()


def summarize_with_gemini(content):
    if not content:
        return '오늘 인수인계 내용이 없습니다.'

    prompt = (
        '다음은 업무 인수인계 내용입니다. '
        '핵심 사항만 간결하게 3~5줄로 요약해주세요. '
        '반드시 한국어로 작성하세요.\n\n'
        f'{content}'
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


def send_kakao_message(access_token, summary):
    template = {
        'object_type': 'text',
        'text': f'📋 오늘의 인수인계 요약\n\n{summary}\n\n— Notion TO-DO LIST 자동 요약',
        'link': {
            'web_url': 'https://www.notion.so/TO-DO-LIST-30bb8f52b84f80999186e42ccce1968f'
        }
    }
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

    print('2. Notion 페이지 읽는 중...')
    content = get_notion_content()
    print(f'   읽은 내용 ({len(content)}자):')
    print(content[:300])

    print('3. Gemini로 요약 중...')
    summary = summarize_with_gemini(content)
    print(f'   요약 결과:\n{summary}')

    print('4. 카카오톡 나에게 보내기...')
    result = send_kakao_message(access_token, summary)
    if result.get('result_code') == 0:
        print('   전송 성공!')
    else:
        raise Exception(f'전송 실패: {result}')
