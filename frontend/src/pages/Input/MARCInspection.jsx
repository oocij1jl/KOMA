import React from 'react';

function flattenFields(fields = []) {
  return fields.flatMap((field) =>
    field.subfields.map((subfield, index) => ({
      id: `${field.tag}-${subfield.code}-${index}`,
      tag: field.tag,
      source: field.source,
      indicator1: field.indicator1,
      indicator2: field.indicator2,
      code: subfield.code,
      value: subfield.value,
      confidence: field.confidence,
      reviewRequired: field.review_required,
      note: field.note,
      evidence: field.evidence,
    }))
  );
}

function sourceLabel(source) {
  if (source === 'ai_inference') return 'AI 추론';
  if (source === 'api') return 'API';
  return source || '-';
}

function SourceBadge({ source }) {
  const isAi = source === 'ai_inference';
  return (
    <span className={`px-2 py-0.5 text-[10px] font-extrabold rounded-full ${isAi ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`}>
      {sourceLabel(source)}
    </span>
  );
}

export default function MARCInspection({ selectedBook, onBackToList }) {
  const result = selectedBook?.result;
  const rows = flattenFields(result?.fields ?? []);
  const skippedFields = result?.skipped_fields ?? [];
  const warnings = result?.warnings ?? [];

  const handleExportJson = () => {
    if (!result) return;

    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `marc-result-${selectedBook.isbn || 'unknown'}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  if (!selectedBook || !result) {
    return (
      <div className="max-w-4xl mx-auto bg-white border border-gray-200 rounded-xl p-8 text-center">
        <h2 className="text-lg font-extrabold text-gray-900">선택된 생성 결과가 없습니다.</h2>
        <button type="button" onClick={onBackToList} className="mt-4 px-5 py-2.5 bg-blue-700 text-white font-bold text-xs rounded-xl hover:bg-blue-800">
          목록으로
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <button
        type="button"
        onClick={onBackToList}
        className="text-blue-600 hover:underline text-xs font-bold"
      >
        목록으로
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">MARC 생성 결과</h2>
          <p className="text-gray-500 text-xs font-bold mt-1">LLM 출력 JSON을 검증한 결과입니다.</p>
        </div>
        <button
          type="button"
          onClick={handleExportJson}
          className="shrink-0 px-4 py-2 bg-gray-900 text-white font-bold text-xs rounded-lg hover:bg-black shadow-sm transition"
        >
          JSON 내보내기
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">ISBN</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block font-mono">{selectedBook.isbn}</span>
        </div>
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">제목</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block truncate">{selectedBook.title}</span>
        </div>
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">생성 필드</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block">{result.fields.length}개</span>
        </div>
      </div>

      {(warnings.length > 0 || skippedFields.length > 0) && (
        <div className="bg-amber-50/60 border border-amber-200 rounded-xl p-4 shadow-sm space-y-3">
          {warnings.length > 0 && (
            <div>
              <h4 className="text-xs font-extrabold text-amber-900">경고</h4>
              <ul className="mt-2 space-y-1 text-amber-800 text-[11px] font-semibold">
                {warnings.map((warning, index) => (
                  <li key={`${warning}-${index}`}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
          {skippedFields.length > 0 && (
            <div>
              <h4 className="text-xs font-extrabold text-amber-900">생성 제외 필드</h4>
              <ul className="mt-2 space-y-1 text-amber-800 text-[11px] font-semibold">
                {skippedFields.map((field, index) => (
                  <li key={`${field.tag}-${index}`}>
                    <span className="font-mono">{field.tag}</span> {field.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="bg-white border border-gray-300 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-white border-b border-gray-200 text-gray-500 font-bold">
                <th className="py-3 px-4">태그</th>
                <th className="py-3 px-4">출처</th>
                <th className="py-3 px-4">지시기호1</th>
                <th className="py-3 px-4">지시기호2</th>
                <th className="py-3 px-4">식별기호</th>
                <th className="py-3 px-4 min-w-[240px]">값</th>
                <th className="py-3 px-4">신뢰도</th>
                <th className="py-3 px-4">검수</th>
                <th className="py-3 px-4 min-w-[260px]">근거</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white font-medium text-gray-800">
              {rows.map((field) => (
                <tr key={field.id} className="hover:bg-gray-50/50 transition-colors align-top">
                  <td className="py-3.5 px-4 font-bold font-mono text-gray-900">{field.tag}</td>
                  <td className="py-3.5 px-4"><SourceBadge source={field.source} /></td>
                  <td className="py-3.5 px-4 text-gray-500 font-mono">{field.indicator1 || ' '}</td>
                  <td className="py-3.5 px-4 text-gray-500 font-mono">{field.indicator2 || ' '}</td>
                  <td className="py-3.5 px-4 text-gray-500 font-mono">${field.code}</td>
                  <td className="py-3.5 px-4 text-gray-900">{field.value}</td>
                  <td className="py-3.5 px-4 text-gray-500 font-bold">{field.confidence}</td>
                  <td className="py-3.5 px-4">
                    {field.reviewRequired ? (
                      <span className="px-2 py-0.5 text-[10px] font-extrabold rounded-full bg-amber-100 text-amber-700">필요</span>
                    ) : (
                      <span className="px-2 py-0.5 text-[10px] font-extrabold rounded-full bg-green-100 text-green-700">불필요</span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 text-gray-500">
                    {field.evidence ? (
                      <div className="space-y-1">
                        <div className="font-bold">{field.evidence.from?.join(', ')}</div>
                        {field.evidence.keywords_used?.length > 0 && (
                          <div>{field.evidence.keywords_used.join(', ')}</div>
                        )}
                        <div>{field.evidence.reasoning}</div>
                      </div>
                    ) : (
                      field.note || '-'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-gray-950 rounded-xl overflow-hidden shadow-sm">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <span className="text-xs font-bold text-gray-300">원본 JSON</span>
          <button
            type="button"
            onClick={handleExportJson}
            className="px-3 py-1.5 bg-white/10 text-white font-bold text-[11px] rounded-md hover:bg-white/20 transition"
          >
            내보내기
          </button>
        </div>
        <pre className="p-4 overflow-x-auto text-xs text-gray-100">
          {JSON.stringify(result, null, 2)}
        </pre>
      </div>
    </div>
  );
}
