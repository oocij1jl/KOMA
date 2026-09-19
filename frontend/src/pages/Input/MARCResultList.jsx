import React, { useState, useMemo } from 'react';

function getStatusBadge(status) {
const styles = {
    완료: 'bg-green-100 text-green-700 font-bold',
    '검수 필요': 'bg-amber-100 text-amber-700 font-bold',
    실패: 'bg-red-100 text-red-700 font-bold',
    '조회 실패': 'bg-red-100 text-red-700 font-bold',
  };

  return (
    <span className={`px-2.5 py-1 text-[11px] rounded-md ${styles[status] || 'bg-gray-100 text-gray-600 font-bold'}`}>
      {status}
    </span>
  );
}

// [MOCK DATA 시작] 개발/테스트 중 데이터가 없을 때 UI 확인용 더미 생성 함수
function getMockResultsIfEmpty() {
  return Array.from({ length: 25 }, (_, i) => ({
    id: `mock-${i + 1}`,
    isbn: `97889364345${(90 + i).toString().padStart(2, '0')}`,
    title: `테스트 도서 ${i + 1} - 대량 데이터 UI 확인용`,
    status: i % 4 === 0 ? '검수 필요' : i % 5 === 0 ? '조회 실패' : '완료',
    createdAt: '2026-09-19 14:00',
    result: {
      fields: new Array((i % 5) + 3).fill(null),
    },
  }));
}
// [MOCK DATA 끝]

export default function MARCResultList({ results = [], onSelectDetail, onCreate }) {

  // [MOCK DATA 시작] 전달된 results가 비어있을 때 테스트용 mock 데이터 적용 (필요 없으면 displayResults = results 로 바로 사용)
  const displayResults = useMemo(() => {
    return results.length > 0 ? results : getMockResultsIfEmpty();
  }, [results]);
  // [MOCK DATA 끝]

  // 대량 조회를 위한 검색, 필터, 페이지네이션 상태
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('ALL');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // 요약 카운트 계산
  const summaryCounts = useMemo(() => {
    const counts = { total: displayResults.length, success: 0, review: 0, fail: 0 };
    displayResults.forEach((item) => {
      if (item.status === '완료') counts.success += 1;
      else if (item.status === '검수 필요') counts.review += 1;
      else if (item.status === '실패' || item.status === '조회 실패') counts.fail += 1;
    });
    return counts;
  }, [displayResults]);

  // 검색어 및 상태별 필터링 연동
  const filteredResults = useMemo(() => {
    return displayResults.filter((item) => {
      const matchesSearch =
        (item.isbn && item.isbn.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (item.title && item.title.toLowerCase().includes(searchQuery.toLowerCase()));

      let matchesStatus = true;
      if (selectedStatus === '완료') matchesStatus = item.status === '완료';
      else if (selectedStatus === '검수 필요') matchesStatus = item.status === '검수 필요';
      else if (selectedStatus === '실패') matchesStatus = item.status === '실패' || item.status === '조회 실패';

      return matchesSearch && matchesStatus;
    });
  }, [displayResults, searchQuery, selectedStatus]);

  // 페이지네이션 계산
  const totalPages = Math.ceil(filteredResults.length / itemsPerPage) || 1;
  const paginatedResults = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return filteredResults.slice(startIndex, startIndex + itemsPerPage);
  }, [filteredResults, currentPage]);

  // 검색/필터 변경 시 페이지 리셋
  const handleSearchChange = (e) => {
    setSearchQuery(e.target.value);
    setCurrentPage(1);
  };

  const handleStatusFilter = (status) => {
    setSelectedStatus(status);
    setCurrentPage(1);
  };

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
{/* 요약 통계 대시보드 카드*/}
      <div className="grid grid-cols-4 gap-4">
        <div
          onClick={() => handleStatusFilter('ALL')}
          className={`p-4 bg-white border rounded-xl shadow-sm cursor-pointer transition ${
            selectedStatus === 'ALL' ? 'ring-2 ring-blue-500 border-transparent' : 'border-gray-200 hover:border-gray-300'
          }`}
        >
          <div className="text-xs font-semibold text-gray-500">전체 요청</div>
          <div className="text-2xl font-extrabold text-gray-900 mt-1">{summaryCounts.total}</div>
        </div>
        <div
          onClick={() => handleStatusFilter('완료')}
          className={`p-4 bg-white border rounded-xl shadow-sm cursor-pointer transition ${
            selectedStatus === '완료' ? 'ring-2 ring-green-500 border-transparent' : 'border-gray-200 hover:border-gray-300'
          }`}
        >
          <div className="text-xs font-semibold text-green-600">완료</div>
          <div className="text-2xl font-extrabold text-green-700 mt-1">{summaryCounts.success}</div>
        </div>
        <div
          onClick={() => handleStatusFilter('검수 필요')}
          className={`p-4 bg-white border rounded-xl shadow-sm cursor-pointer transition ${
            selectedStatus === '검수 필요' ? 'ring-2 ring-amber-500 border-transparent' : 'border-gray-200 hover:border-gray-300'
          }`}
        >
          <div className="text-xs font-semibold text-amber-600">검수 필요</div>
          <div className="text-2xl font-extrabold text-amber-700 mt-1">{summaryCounts.review}</div>
        </div>
        <div
          onClick={() => handleStatusFilter('실패')}
          className={`p-4 bg-white border rounded-xl shadow-sm cursor-pointer transition ${
            selectedStatus === '실패' ? 'ring-2 ring-red-500 border-transparent' : 'border-gray-200 hover:border-gray-300'
          }`}
        >
          <div className="text-xs font-semibold text-red-600">실패 / 오류</div>
          <div className="text-2xl font-extrabold text-red-700 mt-1">{summaryCounts.fail}</div>
        </div>
      </div>

      {/* 검색 및 탭 필터 바 */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-4 border border-gray-200 rounded-xl shadow-sm">
        <div className="flex gap-1 bg-gray-100 p-1 rounded-lg text-xs font-bold w-full sm:w-auto">
          <button
            type="button"
            onClick={() => handleStatusFilter('ALL')}
            className={`px-3 py-1.5 rounded-md transition ${selectedStatus === 'ALL' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            전체 ({summaryCounts.total})
          </button>
          <button
            type="button"
            onClick={() => handleStatusFilter('완료')}
            className={`px-3 py-1.5 rounded-md transition ${selectedStatus === '완료' ? 'bg-white text-green-700 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            완료 ({summaryCounts.success})
          </button>
          <button
            type="button"
            onClick={() => handleStatusFilter('검수 필요')}
            className={`px-3 py-1.5 rounded-md transition ${selectedStatus === '검수 필요' ? 'bg-white text-amber-700 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            검수 필요 ({summaryCounts.review})
          </button>
          <button
            type="button"
            onClick={() => handleStatusFilter('실패')}
            className={`px-3 py-1.5 rounded-md transition ${selectedStatus === '실패' ? 'bg-white text-red-700 shadow-sm' : 'text-gray-500 hover:text-gray-900'}`}
          >
            실패 ({summaryCounts.fail})
          </button>
        </div>

        {/* 검색창 */}
        <div className="w-full sm:w-72">
          <input
            type="text"
            value={searchQuery}
            onChange={handleSearchChange}
            placeholder="ISBN 또는 제목 검색..."
            className="w-full px-3.5 py-2 border border-gray-200 rounded-lg text-xs font-medium focus:outline-none focus:border-blue-500 focus:bg-white transition bg-gray-50"
          />
        </div>
      </div>

      {/* 목록 테이블 영역 */}
      <div className="bg-white border border-gray-300 rounded-xl shadow-sm overflow-hidden">
        {filteredResults.length === 0 ? (
          <div className="p-12 text-center">
            <h3 className="text-sm font-extrabold text-gray-900">검색 또는 필터 결과가 없습니다.</h3>
            <p className="text-xs text-gray-400 font-semibold mt-2">
              {searchQuery ? `'${searchQuery}' 검색어와 일치하는 데이터가 없습니다.` : 'ISBN을 입력해 LLM 기반 MARC 초안을 생성해 주세요.'}
            </p>
          </div>
        ) : (
          <>
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
                {paginatedResults.map((item) => {
                  const fieldCount = item.fields !== undefined 
                    ? item.fields 
                    : item.result?.fields?.length || 0;

                  return (
                    <tr key={item.id} className="hover:bg-gray-50/80 transition-colors">
                      <td className="py-4 px-4 font-mono font-bold text-gray-600">{item.isbn}</td>
                      <td className="py-4 px-4 font-bold text-gray-900">{item.title}</td>
                      <td className="py-4 px-4">{getStatusBadge(item.status)}</td>
                      <td className="py-4 px-4 text-gray-500 font-bold">
                        {item.status === '조회 실패' ? '-' : `${fieldCount}개`}
                      </td>
                      <td className="py-4 px-4 text-gray-400 font-semibold">{item.createdAt || '방금 전'}</td>
                      <td className="py-4 px-4 text-center">
                        <button
                          type="button"
                          onClick={() => onSelectDetail?.(item)}
                          disabled={item.status === '조회 실패'}
                          className={`font-bold ${
                            item.status === '조회 실패'
                              ? 'text-gray-300 cursor-not-allowed'
                              : 'text-blue-600 hover:underline'
                          }`}
                        >
                          상세보기
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* 대량 데이터를 위한 페이지네이션 컨트롤 */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-t border-gray-200 text-xs text-gray-600 font-semibold">
                <div>
                  전체 {filteredResults.length}개 중 {((currentPage - 1) * itemsPerPage) + 1}-
                  {Math.min(currentPage * itemsPerPage, filteredResults.length)}개 표시
                </div>
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => setCurrentPage((prev) => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    이전
                  </button>
                  <span className="px-3 py-1 flex items-center font-bold">
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    type="button"
                    onClick={() => setCurrentPage((prev) => Math.min(prev + 1, totalPages))}
                    disabled={currentPage === totalPages}
                    className="px-3 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    다음
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}