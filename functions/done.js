export async function onRequest(context) {
  const { searchParams } = new URL(context.request.url);
  const blockId = searchParams.get('id');
  const text = searchParams.get('text') || '항목';
  const secret = searchParams.get('secret');

  if (!blockId || secret !== context.env.CALLBACK_SECRET) {
    return new Response('Invalid request', { status: 400 });
  }

  // 1. Notion 체크 처리
  const notionResp = await fetch(`https://api.notion.com/v1/blocks/${blockId}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${context.env.NOTION_API_KEY}`,
      'Notion-Version': '2022-06-28',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ to_do: { checked: true } }),
  });

  if (!notionResp.ok) {
    const err = await notionResp.text();
    return new Response(`Notion 오류: ${err}`, { status: 500 });
  }

  // 2. Kakao 액세스 토큰 발급
  const tokenResp = await fetch('https://kauth.kakao.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: context.env.KAKAO_REST_API_KEY,
      client_secret: context.env.KAKAO_CLIENT_SECRET,
      refresh_token: context.env.KAKAO_REFRESH_TOKEN,
    }),
  });
  const tokenData = await tokenResp.json();

  // 3. 카카오톡 완료 확인 메시지 전송
  if (tokenData.access_token) {
    const decodedText = decodeURIComponent(text);
    const template = {
      object_type: 'text',
      text: `✅ 완료 처리되었습니다\n\n${decodedText}\n\nNotion에 체크되었습니다.`,
      link: {
        web_url: 'https://www.notion.so/TO-DO-LIST-30bb8f52b84f80999186e42ccce1968f',
        mobile_web_url: 'https://www.notion.so/TO-DO-LIST-30bb8f52b84f80999186e42ccce1968f',
      },
    };
    await fetch('https://kapi.kakao.com/v2/api/talk/memo/default/send', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${tokenData.access_token}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        template_object: JSON.stringify(template),
      }),
    });
  }

  // 4. 완료 페이지 반환
  return new Response(
    `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>완료</title>
  <style>
    body { font-family: -apple-system, sans-serif; text-align: center; padding: 60px 20px; background: #f5f5f5; margin: 0; }
    .card { background: white; border-radius: 16px; padding: 40px 24px; max-width: 320px; margin: 0 auto; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
    h1 { font-size: 56px; margin: 0 0 12px; }
    p { color: #333; font-size: 16px; margin: 0 0 8px; word-break: keep-all; }
    small { color: #999; font-size: 13px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>✅</h1>
    <p>완료 처리되었습니다</p>
    <small>Notion에 체크되었습니다</small>
  </div>
</body>
</html>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}
