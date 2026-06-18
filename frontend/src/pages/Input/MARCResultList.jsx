import React from 'react';

function getStatusBadge(status) {
  const styles = {
    완료: 'bg-green-100 text-green-700 font-bold',
    '검수 필요': 'bg-amber-100 text-amber-700 font-bold',
    실패: 'bg-red-100 text-red-700 font-bold',
  };

  return (
    <span className={`px-2 py-0.5 text-[11px] rounded ${styles[status] || 'bg-gray-100 text-gray-600 font-bold'}`}>
      {status}
    </span>
  );
}

export default function MARCResultList({ results = [], onSelectDetail, onCreate }) {
  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">생성 결과</h2>
          <p className="text-gray-500 text-xs font-bold mt-1">총 {results.length}건의 MARC 생성 결과</p>
        </div>
        <button
          type="button"
          onClick={onCreate}
          className="bg-blue-700 hover:bg-blue-800 text-white font-bold text-xs px-4 py-2 rounded-lg shadow-sm"
        >
          새로 생성
        </button>
      </div>

      <div className="bg-white border border-gray-300 rounded-xl shadow-sm overflow-hidden">
        {results.length === 0 ? (
          <div className="p-8 text-center">
            <h3 className="text-sm font-extrabold text-gray-900">아직 생성 결과가 없습니다.</h3>
            <p className="text-xs text-gray-400 font-semibold mt-2">ISBN을 입력해 LLM 기반 MARC 초안을 생성해 주세요.</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-gray-100 border-b border-gray-200 text-gray-600 font-bold">
                <th className="py-3 px-4">ISBN</th>
                <th className="py-3 px-4">제목</th>
                <th className="py-3 px-4">상태</th>
                <th className="py-3 px-4">필드 수</th>
                <th className="py-3 px-4">생성 시각</th>
                <th className="py-3 px-4 text-center">작업</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white font-medium text-gray-700">
              {results.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50/50 transition-colors">
                  <td className="py-4 px-4 font-mono font-bold text-gray-600">{item.isbn}</td>
                  <td className="py-4 px-4 font-bold text-gray-900">{item.title}</td>
                  <td className="py-4 px-4">{getStatusBadge(item.status)}</td>
                  <td className="py-4 px-4 text-gray-500 font-bold">{item.fields}개</td>
                  <td className="py-4 px-4 text-gray-400 font-semibold">{item.createdAt}</td>
                  <td className="py-4 px-4 text-center">
                    <button
                      type="button"
                      onClick={() => onSelectDetail?.(item)}
                      className="text-blue-600 hover:underline font-bold"
                    >
                      상세보기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
