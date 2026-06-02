import React from 'react';

export default function MARCInspection({ selectedBook, onBackToList }) {
  // 목록에서 넘어온 실서지 데이터가 없을 경우 가상 모킹 바인딩
  const book = selectedBook || {
    isbn: '9788901234569',
    title: '책제목책제목',
    fields: 10
  };

  // 테이블 데이터셋 구성 (더미데이터)
  const marcFields = [
    { tag: '001', ind1: '-', ind2: '-', code: '-', val: '-', source: 'AI' },
    { tag: '002', ind1: '-', ind2: '-', code: '-', val: '-', source: 'API' },
    { tag: '002', ind1: '-', ind2: '-', code: '-', val: '-', source: 'API' },
    { tag: '001', ind1: '-', ind2: '-', code: '-', val: '-', source: 'AI' },
    { tag: '002', ind1: '-', ind2: '-', code: '-', val: '-', source: 'API' },
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* 뒤로가기 링크 */}
      <button 
        onClick={onBackToList}
        className="text-blue-600 hover:underline text-xs font-bold flex items-center space-x-1"
      >
        <span>←</span> <span>목록으로</span>
      </button>

      <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">MARC 레코드 검수</h2>

      {/* 상단 서지정보 3단 가로 분할 카드 레이아웃 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">ISBN</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block font-mono">{book.isbn}</span>
        </div>
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">제목</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block truncate">{book.title}</span>
        </div>
        <div className="bg-white border border-gray-300 rounded-xl p-5 shadow-sm">
          <span className="text-[11px] font-bold text-gray-400 block uppercase">생성 필드수</span>
          <span className="text-sm font-extrabold text-gray-900 mt-1 block">{book.fields}개</span>
        </div>
      </div>

      {/* 노란색 경고 배너 보드 안내판 */}
      <div className="bg-amber-50/60 border border-amber-200 rounded-xl p-4 flex items-start space-x-3 shadow-sm">
        <span className="text-amber-600 text-lg font-bold leading-none mt-0.5">⊗</span>
        <div className="space-y-0.5">
          <h4 className="text-xs font-extrabold text-amber-900">검수가 필요한 필드가 있습니다</h4>
          <p className="text-amber-700/80 text-[11px] font-semibold">AI가 추론한 필드는 반드시 검수해주세요</p>
        </div>
      </div>

      {/* MARC 레코드 세부 필드 데이터 테이블 */}
      <div className="bg-white border border-gray-300 rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-white border-b border-gray-200 text-gray-500 font-bold">
              <th className="py-3 px-6">태그</th>
              <th className="py-3 px-4">지시기호1</th>
              <th className="py-3 px-4">지시기호2</th>
              <th className="py-3 px-4">식별기호</th>
              <th className="py-3 px-6">값</th>
              <th className="py-3 px-6">출처</th>
              <th className="py-3 px-6 text-center">작업</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white font-medium text-gray-800">
            {marcFields.map((field, idx) => (
              <tr key={idx} className="hover:bg-gray-50/50 transition-colors">
                <td className="py-3.5 px-6 font-bold font-mono text-gray-900">{field.tag}</td>
                <td className="py-3.5 px-4 text-gray-400 font-mono">{field.ind1}</td>
                <td className="py-3.5 px-4 text-gray-400 font-mono">{field.ind2}</td>
                <td className="py-3.5 px-4 text-gray-400 font-mono">{field.code}</td>
                <td className="py-3.5 px-6 text-gray-400 font-mono">{field.val}</td>
                <td className="py-3.5 px-6">
                  <span className={`px-2 py-0.5 text-[10px] font-extrabold rounded-full ${
                    field.source === 'AI' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
                  }`}>
                    {field.source}
                  </span>
                </td>
                <td className="py-3.5 px-6 text-center space-x-3 font-bold text-[11px]">
                  <button type="button" className="text-blue-600 hover:underline">수정</button>
                  <button type="button" className="text-red-500 hover:underline">삭제</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 하단 기능 제어 바 */}
      <div className="flex items-center justify-between pt-4 border-t border-gray-100">
        <div className="flex space-x-2">
          <button 
            type="button" 
            onClick={() => alert('새로운 KORMARC 식별 필드 행을 추가합니다.')}
            className="px-4 py-2 border border-gray-300 text-gray-800 font-bold text-xs rounded-lg hover:bg-gray-100 transition bg-white shadow-sm"
          >
            필드 추가
          </button>
          <button 
            type="button" 
            onClick={() => alert('KORMARC 규칙 검증 프로토콜을 가동합니다.')}
            className="px-4 py-2 border border-gray-300 text-gray-800 font-bold text-xs rounded-lg hover:bg-gray-100 transition bg-white shadow-sm"
          >
            전체 검증
          </button>
        </div>
        <button
          type="button"
          onClick={onBackToList} // 검수 완료 누르면 다시 목록화면으로
          className="px-5 py-2.5 bg-blue-700 text-white font-bold text-xs rounded-xl hover:bg-blue-800 shadow-md transition-all tracking-wide"
        >
          검수 완료
        </button>
      </div>
    </div>
  );
}