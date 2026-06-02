import React, { useState, useEffect } from 'react';

export default function MARCProgress({ onCancel, onComplete }) {
  // 1. 전체 진행률 상태 (0% ~ 100%)
  const [totalProgress, setTotalProgress] = useState(0);

  // 2. 도서별 진행 상태 더미 데이터
  const [bookTasks, setBookTasks] = useState([
    { id: 1, isbn: '9788901234569', title: '대시보드와 데이터 시각화 개론', status: '대기 중' },
    { id: 2, isbn: '9788901234570', title: 'React와 웹 프론트엔드 실무', status: '대기 중' },
    { id: 3, isbn: '9788901234571', title: 'KORMARC 표준 서지 가이드', status: '대기 중' },
  ]);

  // 3. 실시간 상태 변경 시뮬레이션 효과
  useEffect(() => {
    const interval = setInterval(() => {
      setTotalProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + 1;
      });
    }, 30); // 시뮬레이션 진행 속도

    return () => clearInterval(interval);
  }, []);

  // 진행률 구간별로 개별 도서의 상태를 업데이트하는 효과
  useEffect(() => {
    setBookTasks((prevTasks) =>
      prevTasks.map((task, index) => {
        if (index === 0) {
          if (totalProgress < 30) return { ...task, status: 'API 조회 중' };
          if (totalProgress < 60) return { ...task, status: 'AI 생성 중' };
          return { ...task, status: '완료' };
        }
        if (index === 1) {
          if (totalProgress < 30) return { ...task, status: '대기 중' };
          if (totalProgress < 50) return { ...task, status: 'API 조회 중' };
          if (totalProgress < 85) return { ...task, status: 'AI 생성 중' };
          return { ...task, status: '완료' };
        }
        if (index === 2) {
          if (totalProgress < 60) return { ...task, status: '대기 중' };
          if (totalProgress < 80) return { ...task, status: 'API 조회 중' };
          if (totalProgress < 98) return { ...task, status: 'AI 생성 중' };
          return { ...task, status: '완료' };
        }
        return task;
      })
    );
  }, [totalProgress]);

  // 상태값별 컬러 스타일 매핑
  const getStatusStyle = (status) => {
    switch (status) {
      case '완료': return 'text-green-600 font-bold';
      case 'API 조회 중': return 'text-blue-600 font-bold animate-pulse';
      case 'AI 생성 중': return 'text-purple-600 font-bold animate-pulse';
      case '대기 중': return 'text-gray-400';
      default: return 'text-gray-600';
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* 타이틀 영역 */}
      <div>
        <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">MARC 레코드 자동 생성</h2>
        <p className="text-gray-500 text-sm font-semibold mt-1">AI와 외부 API를 통해 표준 레코드를 구성하고 있습니다.</p>
      </div>

      {/* 1. 전체 진행률 바 영역 */}
      <div className="bg-white border border-gray-300 rounded-xl p-6 shadow-sm space-y-3">
        <div className="flex justify-between items-center text-sm">
          <span className="font-extrabold text-gray-900">전체 진행률</span>
          <span className="font-mono font-bold text-blue-600 text-base">{totalProgress}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-3 overflow-hidden border border-gray-200">
          <div 
            className="bg-blue-600 h-full rounded-full transition-all duration-75 ease-out"
            style={{ width: `${totalProgress}%` }}
          />
        </div>
      </div>

      {/* 2. 도서별 진행 상태 테이블 영역 */}
      <div className="bg-white border border-gray-300 rounded-xl shadow-sm overflow-hidden">
        <div className="p-5 border-b border-gray-200 bg-gray-50/50">
          <h3 className="text-sm font-extrabold text-gray-900">도서별 진행 상태</h3>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-xs font-bold text-gray-500 uppercase tracking-wider">
                <th className="py-3.5 px-6 w-1/4">ISBN</th>
                <th className="py-3.5 px-6 w-2/4">도서명</th>
                <th className="py-3.5 px-6 w-1/4 text-right">상태</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white text-xs">
              {bookTasks.map((task) => (
                <tr key={task.id} className="hover:bg-gray-50/80 transition-colors">
                  <td className="py-4 px-6 font-mono font-semibold text-gray-600">{task.isbn}</td>
                  <td className="py-4 px-6 font-bold text-gray-900 max-w-xs truncate">{task.title}</td>
                  <td className="py-4 px-6 text-right font-medium">
                    <span className={getStatusStyle(task.status)}>
                      {task.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. 하단 네비게이션 영역 (100% 도달 시 결과보기 버튼으로 전환 설정) */}
      <div className="flex items-center justify-between pt-4 border-t border-gray-100">
        {totalProgress < 100 ? (
          <>
            <button
              type="button"
              onClick={onCancel}
              className="px-6 py-2.5 border border-gray-300 text-gray-700 font-bold text-xs rounded-xl hover:bg-gray-100 transition bg-white"
            >
              중단하기
            </button>
            <div className="text-xs font-semibold text-gray-400">
              API 연동 및 레코드 분석이 진행 중입니다...
            </div>
          </>
        ) : (
          <>
            <div className="text-xs font-bold text-green-600 flex items-center space-x-1">
              <span>✓</span> <span>모든 도서의 KORMARC 생성 작업이 완료되었습니다.</span>
            </div>
            <button
              type="button"
              onClick={onComplete}
              className="px-6 py-2.5 bg-blue-600 text-white font-bold text-xs rounded-xl hover:bg-blue-700 shadow-md transition-all tracking-wide flex items-center"
            >
              결과보기 &nbsp;&rarr;
            </button>
          </>
        )}
      </div>

    </div>
  );
}