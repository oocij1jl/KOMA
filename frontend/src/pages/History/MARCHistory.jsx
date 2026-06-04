import React, { useState } from 'react';

// 작업 상태별 표시용 배지 컴포넌트
const StatusBadge = ({ status }) => {
  const styles = {
    완료: 'bg-green-100 text-green-700 border-green-200',
    생성중: 'bg-blue-100 text-blue-700 border-blue-200 animate-pulse',
    실패: 'bg-red-100 text-red-700 border-red-200',
  };
  return (
    <span className={`px-3 py-1 text-xs font-semibold border rounded-full ${styles[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  );
};

export default function MARCHistory({ onSelectTask, onDeleteTask }) {
  // 1. 상태 필터 및 검색어 상태 관리
  const [statusFilter, setStatusFilter] = useState('전체');
  const [searchTerm, setSearchTerm] = useState('');

  // 2. 누적 생성 이력 데이터 셋 (더미 데이터)
  const [historyList, setHistoryList] = useState([
    { id: 4, date: '2026-05-15', taskName: '작업 #4', count: 5, status: '완료' },
    { id: 3, date: '2026-05-15', taskName: '작업 #3', count: 5, status: '완료' },
    { id: 2, date: '2026-05-15', taskName: '작업 #2', count: 5, status: '완료' },
    { id: 1, date: '2026-05-15', taskName: '작업 #1', count: 5, status: '완료' },
    { id: 0, date: '2026-05-15', taskName: '작업 #0', count: 5, status: '실패' },
  ]);

  // 3. 필터 및 검색 조건 적용 로직
  const filteredHistory = historyList.filter(item => {
    const matchesStatus = statusFilter === '전체' || item.status === statusFilter;
    const matchesSearch = item.taskName.toLowerCase().includes(searchTerm.toLowerCase()) || item.date.includes(searchTerm);
    return matchesStatus && matchesSearch;
  });

  // 임시 삭제 핸들러 
  const handleDelete = (id) => {
    if (onDeleteTask) {
      onDeleteTask(id);
    } else {
      if(confirm("정말 삭제하시겠습니까?")) {
        setHistoryList(prev => prev.filter(item => item.id !== id));
      }
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6 p-4">
      {/* 타이틀 영역 */}
      <div>
        <h2 className="text-2xl font-extrabold text-gray-950 tracking-tight">생성 이력</h2>
        <p className="text-gray-500 text-sm mt-1">이전에 생성한 MARC 레코드 목록입니다.</p>
      </div>

      {/* 검색 및 필터 유틸리티 바 */}
      <div className="flex flex-col sm:flex-row gap-3 justify-between items-stretch sm:items-center bg-white p-4 border border-gray-200 rounded-2xl shadow-sm">
        {/* 상태별 필터 탭 */}
        <div className="flex space-x-1">
          {['전체', '완료', '생성중', '실패'].map((status) => (
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
            placeholder="작업명 또는 날짜 검색"
            className="w-full pl-3 pr-8 py-1.5 border border-gray-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-gray-400 bg-gray-50/30"
          />
          <span className="absolute right-2.5 top-2 text-gray-400 text-xs pointer-events-none">🔍</span>
        </div>
      </div>

      {filteredHistory.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-2xl p-12 text-center text-gray-400 font-medium text-sm">
          조건에 일치하는 생성 이력 기록이 존재하지 않습니다.
        </div>
      ) : (
        <div className="border border-gray-300 rounded-2xl overflow-hidden bg-white shadow-sm">
          <table className="w-full border-collapse text-sm text-left">
            {/* 테이블 헤더 */}
            <thead>
              <tr className="bg-[#e5e7eb]/60 border-b border-gray-300 text-gray-600 text-xs font-semibold">
                <th className="py-3 px-6 w-1/4">날짜</th>
                <th className="py-3 px-6 w-1/4">레코드 수</th>
                <th className="py-3 px-6 w-1/4">상태</th>
                <th className="py-3 px-6 w-1/4 text-center">작업</th>
              </tr>
            </thead>
            
            {/* 테이블 바디  */}
            <tbody className="divide-y divide-gray-300 font-medium text-gray-800">
              {filteredHistory.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50/50 transition-colors">
                  {/* 날짜 */}
                  <td className="py-4 px-6 text-gray-700">{item.date}</td>
                  
                  {/* 레코드 수 */}
                  <td className="py-4 px-6">{item.count}건</td>
                  
                  {/* 상태 배지 */}
                  <td className="py-4 px-6">
                    <StatusBadge status={item.status} />
                  </td>
                  
                  {/* 작업 버튼 (다시 열기 / 삭제) */}
                  <td className="py-4 px-6 text-center space-x-4 text-xs font-bold">
                    <button
                      onClick={() => onSelectTask && onSelectTask(item)}
                      className="text-blue-600 hover:underline transition"
                    >
                      다시 열기
                    </button>
                    <button
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