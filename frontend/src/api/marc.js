const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

function readErrorMessage(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload.detail === 'string') return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join('\n');
  }
  if (typeof payload.message === 'string') return payload.message;
  return fallback;
}

export async function generateMarcByIsbn(isbn) {
  const response = await fetch(`${API_BASE_URL}/api/generate/marc`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ isbn }),
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new Error(readErrorMessage(payload, 'MARC 생성 요청에 실패했습니다.'));
  }

  return payload;
}
