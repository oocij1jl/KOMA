import React, { useState } from 'react';
import MARCExportModal from './MARCExportModal'; // 내보내기 모달 팝업 임포트

export default function MARCResultList({ onSelectDetail }) {
  const [filter, setFilter] = useState('전체');
  const [isExportOpen, setIsExportOpen] = useState(false); // 모달의 열림/닫힘 제어 플래그 변수

  // 책 정보 더미데이터
  const [results] = useState([
    { id: 1, isbn: '9788901234567', title: '어린왕자', status: '완료', fields: 12 },
    { id: 2, isbn: '9788901234568', title: '데미안', status: '완료', fields: 11 },
    { id: 3, isbn: '9788901234569', title: '소년이 온다', status: '검수 필요', fields: 10 },
    { id: 4, isbn: '9788901234570', title: '채식주의자', status: '검수 필요', fields: 9 },
    { id: 5, isbn: '9788901234571', title: '작별하지 않는다', status: '실패', fields: 8 },
  ]);

  const filteredResults = results.filter(item => {
    if (filter === '전체') return true;
    return item.status === filter;
  });

  const getStatusBadge = (status) => {
    const styles = {
      완료: 'bg-green-100 text-green-700 font-bold',
      '검수 필요': 'bg-amber-100 text-amber-700 font-bold',
      실패: 'bg-red-100 text-red-700 font-bold',
    };
    return (
      <span className={`px-2 py-0.5 text-[11px] rounded ${styles[status]}`}>
        {status}
      </span>
    );
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* 상단 타이틀 및 내보내기 버튼 */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">생성 결과</h2>
          <p className="text-gray-500 text-xs font-bold mt-1">총 5건의 레코드</p>
        </div>
        <button 
          onClick={() => setIsExportOpen(true)} // 내보내기 모달 트리거 활성화
          className="bg-blue-700 hover:bg-blue-800 text-white font-bold text-xs px-4 py-2 rounded-lg shadow-sm flex items-center space-x-1"
        >
          <span>⤓</span> <span>내보내기</span>
        </button>
      </div>

      {/* 필터 탭 바 */}
      <div className="flex space-x-2">
        {[
          { name: '전체', count: 5 },
          { name: '완료', count: 2 },
          { name: '검수 필요', count: 2 },
          { name: '실패', count: 1 }
        ].map((tab) => (
          <button
            key={tab.name}
            onClick={() => setFilter(tab.name)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
              filter === tab.name 
                ? 'bg-blue-100 text-blue-700 border border-blue-200' 
                : 'bg-gray-100 text-gray-500 border border-transparent hover:bg-gray-200'
            }`}
          >
            {tab.name} ({tab.count})
          </button>
        ))}
      </div>

      {/* 데이터 테이블 박스 */}
      <div className="bg-white border border-gray-300 rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-gray-100 border-b border-gray-200 text-gray-600 font-bold">
              <th className="py-3 px-4 w-12 text-center">
                <input type="checkbox" className="rounded border-gray-300" />
              </th>
              <th className="py-3 px-4">ISBN</th>
              <th className="py-3 px-4">제목</th>
              <th className="py-3 px-4">상태</th>
              <th className="py-3 px-4">필드 수</th>
              <th className="py-3 px-4 text-center">작업</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white font-medium text-gray-700">
            {filteredResults.map((item) => (
              <tr key={item.id} className="hover:bg-gray-50/50 transition-colors">
                <td className="py-4 px-4 text-center">
                  <input type="checkbox" className="rounded border-gray-300" />
                </td>
                <td className="py-4 px-4 font-mono font-bold text-gray-600">{item.isbn}</td>
                <td className="py-4 px-4 font-bold text-gray-900">{item.title}</td>
                <td className="py-4 px-4">{getStatusBadge(item.status)}</td>
                <td className="py-4 px-4 text-gray-400 font-bold">{item.fields}개</td>
                <td className="py-4 px-4 text-center">
                  <button
                    onClick={() => onSelectDetail(item)}
                    className="text-blue-600 hover:underline font-bold"
                  >
                    상세보기
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 조건부 렌더링을 통한 내보내기 모달 오버레이 표출 제어판 구역 */}
      {isExportOpen && (
        <MARCExportModal onClose={() => setIsExportOpen(false)} />
      )}
    </div>
  );
}