import React, { useState } from 'react';

// 작업 상태별 표시용 배지 컴포넌트
const StatusBadge = ({ status }) => {
  const styles = {
    완료: 'bg-green-100 text-green-700 border-green-200',
    '검수 필요': 'bg-amber-100 text-amber-700 border-amber-200',
    '조회 실패': 'bg-red-100 text-red-700 border-red-200',
  };
  return (
    <span className={`px-3 py-1 text-xs font-semibold border rounded-full ${styles[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  );
};

const STATUS_OPTIONS = ['전체', '완료', '검수 필요', '조회 실패'];

export default function MARCHistory({ results = [], onSelectTask, onDeleteTask }) {
  // 1. 상태 필터 및 검색어 상태 관리
  const [statusFilter, setStatusFilter] = useState('전체');
  const [searchTerm, setSearchTerm] = useState('');

  // 2. 이번 세션에서 실제로 생성한 결과(HomeDashboard의 generatedResults)를 그대로 이력으로 쓴다.
  //    새로고침하면 사라지는 건 DB가 없어서다(저장은 export 파일로만 함) — 의도된 동작.

  // 3. 필터 및 검색 조건 적용 로직
  const filteredHistory = results.filter((item) => {
    const matchesStatus = statusFilter === '전체' || item.status === statusFilter;
    const term = searchTerm.toLowerCase();
    const matchesSearch =
      !term ||
      (item.title && item.title.toLowerCase().includes(term)) ||
      (item.isbn && item.isbn.toLowerCase().includes(term));
    return matchesStatus && matchesSearch;
  });

  const handleDelete = (id) => {
    if (onDeleteTask && confirm('정말 삭제하시겠습니까?')) {
      onDeleteTask(id);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6 p-4">
      {/* 타이틀 영역 */}
      <div>
        <h2 className="text-2xl font-extrabold text-gray-950 tracking-tight">생성 이력</h2>
        <p className="text-gray-500 text-sm mt-1">
          이번 세션에서 생성한 MARC 레코드 목록입니다. (새로고침 시 초기화됩니다 — 보관하려면 내보내기를 이용하세요)
        </p>
      </div>

      {/* 검색 및 필터 유틸리티 바 */}
      <div className="flex flex-col sm:flex-row gap-3 justify-between items-stretch sm:items-center bg-white p-4 border border-gray-200 rounded-2xl shadow-sm">
        {/* 상태별 필터 탭 */}
        <div className="flex space-x-1">
          {STATUS_OPTIONS.map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setStatusFilter(status)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-all ${
                statusFilter === status
                  ? 'bg-gray-900 text-white border-gray-900'
                  : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
              }`}
            >
              {status}
            </button>
          ))}
        </div>

        {/* 통합 검색창 */}
        <div className="relative max-w-xs w-full">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="제목 또는 ISBN 검색"
            className="w-full pl-3 pr-8 py-1.5 border border-gray-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-gray-400 bg-gray-50/30"
          />
          <span className="absolute right-2.5 top-2 text-gray-400 text-xs pointer-events-none">🔍</span>
        </div>
      </div>

      {filteredHistory.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-2xl p-12 text-center text-gray-400 font-medium text-sm">
          {results.length === 0
            ? '아직 생성한 MARC 레코드가 없습니다. ISBN을 입력해 생성해 보세요.'
            : '조건에 일치하는 생성 이력 기록이 존재하지 않습니다.'}
        </div>
      ) : (
        <div className="border border-gray-300 rounded-2xl overflow-hidden bg-white shadow-sm">
          <table className="w-full border-collapse text-sm text-left">
            {/* 테이블 헤더 */}
            <thead>
              <tr className="bg-[#e5e7eb]/60 border-b border-gray-300 text-gray-600 text-xs font-semibold">
                <th className="py-3 px-6">생성 시각</th>
                <th className="py-3 px-6">ISBN</th>
                <th className="py-3 px-6">제목</th>
                <th className="py-3 px-6">필드 수</th>
                <th className="py-3 px-6">상태</th>
                <th className="py-3 px-6 text-center">작업</th>
              </tr>
            </thead>

            {/* 테이블 바디  */}
            <tbody className="divide-y divide-gray-300 font-medium text-gray-800">
              {filteredHistory.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50/50 transition-colors">
                  <td className="py-4 px-6 text-gray-500 font-semibold">{item.createdAt || '-'}</td>
                  <td className="py-4 px-6 font-mono text-gray-700">{item.isbn}</td>
                  <td className="py-4 px-6 font-bold text-gray-900">{item.title}</td>
                  <td className="py-4 px-6">{item.fields ?? item.result?.fields?.length ?? 0}건</td>
                  <td className="py-4 px-6">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="py-4 px-6 text-center space-x-4 text-xs font-bold">
                    <button
                      type="button"
                      onClick={() => onSelectTask && onSelectTask(item)}
                      disabled={item.status === '조회 실패'}
                      className={item.status === '조회 실패' ? 'text-gray-300 cursor-not-allowed' : 'text-blue-600 hover:underline transition'}
                    >
                      다시 열기
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(item.id)}
                      className="text-red-500 hover:underline transition"
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
