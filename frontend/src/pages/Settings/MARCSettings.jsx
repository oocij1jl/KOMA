import React, { useState } from 'react';

export default function MARCSettings() {
  // 1. 기본 생성 옵션 체크박스 상태 관리 (초기값 전부 true)
  const [options, setOptions] = useState({
    includeSourceDefault: true,
    autoAiInference: true,
    showNotification: true,
  });

  // 토글 제어 핸들러
  const handleToggle = (key) => {
    setOptions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // 오래된 이력 정리 액션 핸들러
  const handleClearOldHistory = () => {
    if (window.confirm('오래된 이력 데이터를 삭제하여 브라우저 저장 공간을 확보하시겠습니까?')) {
      alert('오래된 이력 정리가 완료되었습니다. (0.0 MB / 50 MB)');
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* 타이틀 영역 */}
      <div>
        <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">설정</h2>
        <p className="text-gray-500 text-sm font-semibold mt-1">API 키 및 시스템 기본 작동 옵션을 관리합니다.</p>
      </div>

      {/* 1. 기본 생성 옵션 박스 영역 */}
      <div className="bg-white border border-gray-300 rounded-xl p-6 space-y-5 shadow-sm">
        <h3 className="text-base font-extrabold text-gray-900">기본 생성 옵션</h3>
        <div className="space-y-4">
          <label className="flex items-center space-x-3 cursor-pointer select-none text-gray-900 font-bold text-xs">
            <input
              type="checkbox"
              checked={options.includeSourceDefault}
              onChange={() => handleToggle('includeSourceDefault')}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <span>출처 표시 기본값으로 포함</span>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer select-none text-gray-900 font-bold text-xs">
            <input
              type="checkbox"
              checked={options.autoAiInference}
              onChange={() => handleToggle('autoAiInference')}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <span>AI 추론 필드 자동 생성</span>
          </label>

          <label className="flex items-center space-x-3 cursor-pointer select-none text-gray-900 font-bold text-xs">
            <input
              type="checkbox"
              checked={options.showNotification}
              onChange={() => handleToggle('showNotification')}
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <span>생성 완료 시 알림 표시</span>
          </label>
        </div>
      </div>

      {/* 2. 저장 공간 관리 박스 영역 */}
      <div className="bg-white border border-gray-300 rounded-xl p-6 space-y-4 shadow-sm">
        <h3 className="text-base font-extrabold text-gray-900">저장 공간 관리</h3>
        
        <div className="space-y-2">
          {/* 용량 텍스트 라인 */}
          <div className="flex justify-between items-center text-xs font-bold">
            <span className="text-gray-500">사용 중인 저장 공간</span>
            <span className="text-gray-900 font-mono text-right">2.3 MB / 50 MB</span>
          </div>
          
          {/* 와이어프레임 진행 막대 바 트랙 */}
          <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
            {/* 2.3MB 수치 비율에 맞춘 인디케이터 바 */}
            <div className="bg-blue-600 h-full rounded-full" style={{ width: '4.6%' }} />
          </div>
        </div>

        {/* 하단 붉은색 제어 액션 앵커 단추 */}
        <div className="pt-2">
          <button
            type="button"
            onClick={handleClearOldHistory}
            className="text-red-600 hover:text-red-800 text-[11px] font-bold transition-colors hover:underline"
          >
            오래된 이력 정리
          </button>
        </div>
      </div>
    </div>
  );
}