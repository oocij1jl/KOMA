import React, { useState, useEffect } from 'react'; // [수정] useState, useEffect 훅 호출
import { validateMarcFields, exportMarc } from '../../api/marc';

function flattenFields(fields = []) {
  if (!Array.isArray(fields)) return [];

  return fields.flatMap((field, fieldIdx) => {
    // subfields가 없거나 null/undefined인 필드(예: 제어필드 등) 안전 처리
    const subfields = Array.isArray(field?.subfields) ? field.subfields : [];

    // subfields가 아예 비어있는 경우(단일 value 필드 등) 처리
    if (subfields.length === 0) {
      return [{
        id: `${field?.tag || 'tag'}-${fieldIdx}`,
        fieldIndex: fieldIdx,
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
      fieldIndex: fieldIdx,
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

// flattenFields의 역변환: 편집된 행(subfield 단위)을 다시 원래 필드 경계(fieldIndex)
// 기준으로 묶어서 백엔드가 기대하는 { tag, indicator1, indicator2, subfields } 배열로 만든다.
function buildFieldsFromRows(rows) {
  const groups = new Map();
  const order = [];

  rows.forEach((row) => {
    const key = row.fieldIndex ?? row.id;
    if (!groups.has(key)) {
      groups.set(key, {
        tag: (row.tag || '').trim(),
        indicator1: row.indicator1 || ' ',
        indicator2: row.indicator2 || ' ',
        subfields: [],
      });
      order.push(key);
    }
    const value = (row.value ?? '').trim();
    if (value) {
      groups.get(key).subfields.push({ code: row.code || 'a', value });
    }
  });

  return order
    .map((key) => groups.get(key))
    .filter((field) => field.tag && field.subfields.length > 0);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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
  const [validationResult, setValidationResult] = useState(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

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
    const nextFieldIndex = rows.length
      ? Math.max(...rows.map((row) => row.fieldIndex ?? 0)) + 1
      : 0;
    const newRow = {
      id: `new-${Date.now()}`,
      fieldIndex: nextFieldIndex,
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
    // rows는 subfield 단위로 펼쳐진 편집용 표현이라 그대로 fields에 넣으면 모양이
    // 깨진다. buildFieldsFromRows로 { tag, indicator1, indicator2, subfields } 꼴로
    // 되돌린 뒤 저장한다(export와 동일한 재조립 로직 재사용).
    const updatedFields = buildFieldsFromRows(rows);
    const updatedBook = {
      ...selectedBook,
      status: '완료',
      result: {
        ...selectedBook.result,
        fields: updatedFields,
      },
    };

    // 상위 컴포넌트(HomeDashboard)에 반영 — 이게 없으면 편집이 목록/선택 상태에
    // 전혀 반영되지 않고 로컬 alert만 뜨는 채로 끝난다.
    if (onSave) {
      onSave(updatedBook);
    }

    setIsSaved(true);
    alert('수정사항이 성공적으로 저장되었습니다!');
  };

  // 편집된 행을 서버 검증 규칙(/api/validate)으로 다시 검증한다.
  const handleRevalidate = async () => {
    const fields = buildFieldsFromRows(rows);
    if (!fields.length) {
      setValidationResult(null);
      return alert('검증할 필드가 없습니다.');
    }
    setIsValidating(true);
    try {
      const result = await validateMarcFields(fields);
      setValidationResult(result);
    } catch (error) {
      alert(error instanceof Error ? error.message : '검증 요청에 실패했습니다.');
    } finally {
      setIsValidating(false);
    }
  };

  // 실제 MARC 파일(.mrc 바이너리 / .mrk 텍스트)로 내보낸다.
  const handleExportMarc = async (format) => {
    const fields = buildFieldsFromRows(rows);
    if (!fields.length) return alert('내보낼 필드가 없습니다.');

    setIsExporting(true);
    try {
      const blob = await exportMarc(fields, format);
      const ext = format === 'mrc' ? 'mrc' : 'mrk';
      downloadBlob(blob, `MARC_EDITED_${selectedBook?.isbn || 'result'}.${ext}`);
    } catch (error) {
      alert(error instanceof Error ? error.message : 'MARC 내보내기 요청에 실패했습니다.');
    } finally {
      setIsExporting(false);
    }
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
            onClick={handleRevalidate}
            disabled={isValidating}
            className="px-3 py-2 bg-amber-500 text-white font-bold text-xs rounded-lg hover:bg-amber-600 shadow-sm transition disabled:opacity-50"
          >
            {isValidating ? '검증 중...' : '재검증'}
          </button>
          <button
            type="button"
            onClick={() => handleExportMarc('mrk')}
            disabled={isExporting}
            className="px-4 py-2 bg-blue-600 text-white font-bold text-xs rounded-lg hover:bg-blue-700 shadow-sm transition disabled:opacity-50"
          >
            MARC 저장(.mrk)
          </button>
          <button
            type="button"
            onClick={() => handleExportMarc('mrc')}
            disabled={isExporting}
            className="px-4 py-2 bg-blue-700 text-white font-bold text-xs rounded-lg hover:bg-blue-800 shadow-sm transition disabled:opacity-50"
          >
            MARC 저장(.mrc)
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

      {validationResult && (
        <div
          className={`border rounded-xl p-4 shadow-sm space-y-2 ${
            validationResult.valid ? 'bg-green-50/60 border-green-200' : 'bg-red-50/60 border-red-200'
          }`}
        >
          <h4 className={`text-xs font-extrabold ${validationResult.valid ? 'text-green-900' : 'text-red-900'}`}>
            재검증 결과: {validationResult.valid ? '통과' : `오류 ${validationResult.error_count}건`}
            {validationResult.warning_count > 0 && ` / 경고 ${validationResult.warning_count}건`}
          </h4>
          {validationResult.errors?.length > 0 && (
            <ul className="space-y-1 text-red-800 text-[11px] font-semibold">
              {validationResult.errors.map((err, index) => (
                <li key={`err-${index}`}><span className="font-mono">[{err.field}]</span> {err.message}</li>
              ))}
            </ul>
          )}
          {validationResult.warnings?.length > 0 && (
            <ul className="space-y-1 text-amber-800 text-[11px] font-semibold">
              {validationResult.warnings.map((warn, index) => (
                <li key={`warn-${index}`}><span className="font-mono">[{warn.field}]</span> {warn.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}

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