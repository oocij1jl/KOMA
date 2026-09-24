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

// 여러 ISBN을 한 번에 생성한다. 서버가 한 번에 최대 10개까지만 받으므로
// 그보다 많으면 호출 측(MARCInput.jsx)에서 10개씩 나눠 보낸다.
export async function generateMarcBulk(isbns) {
  const response = await fetch(`${API_BASE_URL}/api/generate/marc/bulk`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ isbns }),
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new Error(readErrorMessage(payload, 'MARC 다건 생성 요청에 실패했습니다.'));
  }

  return payload; // { total, results: [{ isbn, status, result?, error_code?, error_message? }] }
}

// 편집된 필드 배열을 서버 쪽 1차 형식 검증 규칙으로 재검증한다.
export async function validateMarcFields(fields) {
  const response = await fetch(`${API_BASE_URL}/api/validate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ fields }),
  });

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new Error(readErrorMessage(payload, 'MARC 검증 요청에 실패했습니다.'));
  }

  return payload; // { valid, error_count, warning_count, errors, warnings }
}

// 편집된 필드 배열을 실제 MARC 파일(.mrc/.mrk) 또는 json으로 내려받는다.
export async function exportMarc(fields, format) {
  const response = await fetch(`${API_BASE_URL}/api/export/marc`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ fields, format }),
  });

  if (!response.ok) {
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    throw new Error(readErrorMessage(payload, 'MARC 내보내기 요청에 실패했습니다.'));
  }

  return response.blob();
}
