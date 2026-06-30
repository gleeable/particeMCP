export async function onRequest(context) {
  const { searchParams } = new URL(context.request.url);
  const blockId = searchParams.get('id');
  const secret = searchParams.get('secret');

  if (!blockId || secret !== context.env.CALLBACK_SECRET) {
    return new Response('Invalid request', { status: 400 });
  }

  const resp = await fetch(`https://api.notion.com/v1/blocks/${blockId}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${context.env.NOTION_API_KEY}`,
      'Notion-Version': '2022-06-28',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ to_do: { checked: true } }),
  });

  if (resp.ok) {
    return new Response(
      `<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>완료</title>
<style>
  body { font-family: -apple-system, sans-serif; text-align: center; padding: 60px 20px; background: #f5f5f5; }
  .card { background: white; border-radius: 16px; padding: 40px; max-width: 320px; margin: 0 auto; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
  h1 { font-size: 48px; margin: 0 0 16px; }
  p { color: #555; font-size: 16px; }
</style>
</head>
<body>
  <div class="card">
    <h1>✅</h1>
    <p>Notion에 완료 처리되었습니다.</p>
  </div>
</body>
</html>`,
      { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
  }

  const error = await resp.text();
  return new Response(`오류가 발생했습니다: ${error}`, { status: 500 });
}
