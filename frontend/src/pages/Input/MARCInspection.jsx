import React, { useState, useEffect } from 'react'; // [수정] useState, useEffect 훅 호출

function flattenFields(fields = []) {
  if (!Array.isArray(fields)) return [];

  return fields.flatMap((field, fieldIdx) => {
    // subfields가 없거나 null/undefined인 필드(예: 제어필드 등) 안전 처리
    const subfields = Array.isArray(field?.subfields) ? field.subfields : [];

    // subfields가 아예 비어있는 경우(단일 value 필드 등) 처리
    if (subfields.length === 0) {
      return [{
        id: `${field?.tag || 'tag'}-${fieldIdx}`,
        tag: field?.tag || '',
        source: field?.source || 'user',
        indicator1: field?.indicator1 ?? ' ',
        indicator2: field?.indicator2 ?? ' ',
        code: '',
        value: field?.value || '',
        confidence: field?.confidence ?? 1.0,
        reviewRequired: field?.review_required ?? false,
        note: field?.note || '',
        evidence: field?.evidence || null,
      }];
    }

    return subfields.map((subfield, index) => ({
      id: `${field.tag}-${subfield?.code || 'a'}-${fieldIdx}-${index}`,
      tag: field.tag || '',
      source: field.source || 'user',
      indicator1: field.indicator1 ?? ' ',
      indicator2: field.indicator2 ?? ' ',
      code: subfield?.code || 'a',
      value: subfield?.value || '',
      confidence: field.confidence ?? 1.0,
      reviewRequired: field.review_required ?? false,
      note: field.note || '',
      evidence: field.evidence || null,
    }));
  });
}

function sourceLabel(source) {
  if (source === 'ai_inference') return 'AI 추론';
  if (source === 'api') return 'API';
  if (source === 'user') return '수동 수정';
  return source || '-';
}

function SourceBadge({ source }) {
  const isAi = source === 'ai_inference';
  const isUser = source === 'user';
  return (
    <span
      className={`px-2 py-0.5 text-[10px] font-extrabold rounded-full ${
        isAi
          ? 'bg-purple-100 text-purple-700'
          : isUser
          ? 'bg-emerald-100 text-emerald-700'
          : 'bg-blue-100 text-blue-700'
      }`}
    >
      {sourceLabel(source)}
    </span>
  );
}

export default function MARCInspection({ selectedBook, onBackToList, onSave }) {
  const result = selectedBook?.result;
  
  const [isSaved, setIsSaved] = useState(true);

 const [rows, setRows] = useState(() => {
  if (selectedBook && selectedBook.result && selectedBook.result.fields) {
    return flattenFields(selectedBook.result.fields);
  }
  return [];
});

  useEffect(() => {
    if (result?.fields) {
      setRows(flattenFields(result.fields));
    }
  }, [result]);

  const skippedFields = result?.skipped_fields ?? [];
  const warnings = result?.warnings ?? [];

  // 셀 수정 / 행 추가 / 행 삭제 핸들러
  const handleCellChange = (id, fieldName, newValue) => {
    setIsSaved(false);
    setRows((prevRows) =>
      prevRows.map((row) =>
        row.id === id ? { ...row, [fieldName]: newValue, source: 'user' } : row
      )
    );
  };

  const handleAddRow = () => {
    setIsSaved(false);
    const newRow = {
      id: `new-${Date.now()}`,
      tag: '245',
      source: 'user',
      indicator1: '0',
      indicator2: '0',
      code: 'a',
      value: '',
      confidence: 1.0,
      reviewRequired: false,
      note: '사용자 직접 추가',
      evidence: null,
    };
    setRows((prev) => [...prev, newRow]);
  };

  const handleDeleteRow = (id) => {
    setIsSaved(false);
    setRows((prev) => prev.filter((row) => row.id !== id));
  };

  const handleSave = () => {
    const updatedBook = {
      ...selectedBook,
      status: '완료', 
      result: {
        ...selectedBook.result,
        fields: rows, // 수정된 필드 데이터 저장
      },
    };

    // 상위 컴포넌트(HomeDashboard 등)에 전달 함수가 있는 경우 전달
    if (onSave) {
      onSave(updatedBook);
    }

    setIsSaved(true);
    alert('수정사항이 성공적으로 저장되었습니다!');
  };

  // MARC TXT 파일 다운로드 기능 (더미/실제 공용)
  const handleExportText = () => {
    if (!rows.length) return alert('저장할 데이터가 없습니다.');

    const textLines = rows.map(
      (r) => `${r.tag} ${r.indicator1 || ' '}${r.indicator2 || ' '} $${r.code}${r.value}`
    );
    const content = textLines.join('\n');

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `MARC_EDITED_${selectedBook?.isbn || 'result'}.txt`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  // JSON 내보내기
  const handleExportJson = () => {
    if (!result) return;

    const exportData = {
      ...result,
      edited_fields: rows,
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
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
        <button
          type="button"
          onClick={onBackToList}
          className="mt-4 px-5 py-2.5 bg-blue-700 text-white font-bold text-xs rounded-xl hover:bg-blue-800"
        >
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
        
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSave}
            className={`px-3 py-2 text-white font-bold text-xs rounded-lg shadow-sm transition ${
              isSaved ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-orange-500 hover:bg-orange-600 animate-pulse'
            }`}
          >
            {isSaved ? '저장됨' : '수정사항 저장'}
          </button>
          <button
            type="button"
            onClick={handleAddRow}
            className="px-3 py-2 bg-emerald-600 text-white font-bold text-xs rounded-lg hover:bg-emerald-700 shadow-sm transition"
          >
            + 필드 추가
          </button>
          <button
            type="button"
            onClick={handleExportText}
            className="px-4 py-2 bg-blue-600 text-white font-bold text-xs rounded-lg hover:bg-blue-700 shadow-sm transition"
          >
            TXT 저장
          </button>
          <button
            type="button"
            onClick={handleExportJson}
            className="shrink-0 px-4 py-2 bg-gray-900 text-white font-bold text-xs rounded-lg hover:bg-black shadow-sm transition"
          >
            JSON 내보내기
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">ISBN</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block font-mono">
            {selectedBook.isbn}
          </span>
        </div>
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">제목</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block truncate">
            {selectedBook.title}
          </span>
        </div>
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">생성 필드</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block">
            {rows.length}개
          </span>
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

      {/* MARC 테이블 영역 */}
      <div className="bg-white border border-gray-300 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-white border-b border-gray-200 text-gray-500 font-bold">
                <th className="py-3 px-4 w-20">태그</th>
                <th className="py-3 px-3 w-24">출처</th>
                <th className="py-3 px-2 w-16 text-center">지시기호1</th>
                <th className="py-3 px-2 w-16 text-center">지시기호2</th>
                <th className="py-3 px-3 w-20">식별기호</th>
                <th className="py-3 px-4 min-w-[240px]">값</th>
                <th className="py-3 px-3 w-16">신뢰도</th>
                <th className="py-3 px-3 w-20">검수</th>
                <th className="py-3 px-4 min-w-[220px]">근거</th>
                <th className="py-3 px-3 w-16 text-center">관리</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white font-medium text-gray-800">
              {rows.map((field) => (
                <tr key={field.id} className="hover:bg-gray-50/50 transition-colors align-top">
                  
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      maxLength={3}
                      value={field.tag}
                      onChange={(e) => handleCellChange(field.id, 'tag', e.target.value)}
                      className="w-12 font-mono font-bold text-gray-900 border border-gray-300 rounded px-1.5 py-1 text-xs focus:ring-1 focus:ring-blue-500 focus:outline-none"
                    />
                  </td>

                  <td className="py-2.5 px-3 whitespace-nowrap">
                    <SourceBadge source={field.source} />
                  </td>

                  <td className="py-2 px-2 text-center">
                    <input
                      type="text"
                      maxLength={1}
                      value={field.indicator1}
                      onChange={(e) => handleCellChange(field.id, 'indicator1', e.target.value)}
                      className="w-7 text-center font-mono border border-gray-300 rounded py-1 text-xs focus:ring-1 focus:ring-blue-500 focus:outline-none"
                    />
                  </td>

                  <td className="py-2 px-2 text-center">
                    <input
                      type="text"
                      maxLength={1}
                      value={field.indicator2}
                      onChange={(e) => handleCellChange(field.id, 'indicator2', e.target.value)}
                      className="w-7 text-center font-mono border border-gray-300 rounded py-1 text-xs focus:ring-1 focus:ring-blue-500 focus:outline-none"
                    />
                  </td>

                  <td className="py-2 px-3">
                    <div className="flex items-center space-x-0.5">
                      <span className="text-gray-400 font-mono">$</span>
                      <input
                        type="text"
                        maxLength={2}
                        value={field.code}
                        onChange={(e) => handleCellChange(field.id, 'code', e.target.value)}
                        className="w-7 font-mono border border-gray-300 rounded px-1 py-1 text-xs focus:ring-1 focus:ring-blue-500 focus:outline-none"
                      />
                    </div>
                  </td>

                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={field.value}
                      onChange={(e) => handleCellChange(field.id, 'value', e.target.value)}
                      className="w-full border border-gray-300 rounded px-2 py-1 text-xs font-medium text-gray-900 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                    />
                  </td>

                  <td className="py-3 px-3 text-gray-500 font-bold">{field.confidence}</td>

                  <td className="py-2.5 px-3 whitespace-nowrap">
                    {field.reviewRequired ? (
                      <span className="inline-block whitespace-nowrap px-2 py-0.5 text-[10px] font-extrabold rounded-full bg-amber-100 text-amber-700">
                        필요
                      </span>
                    ) : (
                      <span className="inline-block whitespace-nowrap px-2 py-0.5 text-[10px] font-extrabold rounded-full bg-green-100 text-green-700">
                        불필요
                      </span>
                    )}
                  </td>

                  <td className="py-3 px-4 text-gray-500">
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

                  <td className="py-2 px-3 text-center whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => handleDeleteRow(field.id)}
                      className="text-red-500 hover:text-red-700 font-bold transition text-xs"
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 원본 JSON 박스 */}
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