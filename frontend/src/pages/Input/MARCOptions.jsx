import React, { useState } from 'react';

export default function MARCOptions({ onPrev, onStartGeneration }) {
  // 1. 선택 필드 체크박스 상태 관리 (초기값 모두 체크)
  const [selectedFields, setSelectedFields] = useState({
    author: true,
    publisher: true,
    subject: true,
  });

  // 2. 출처 표시 포함 체크박스 상태 관리
  const [includeSource, setIncludeSource] = useState(true);

  // 선택 필드 토글 핸들러
  const handleCheckboxChange = (field) => {
    setSelectedFields((prev) => ({ ...prev, [field]: !prev[field] }));
  };

  // 다음 단계 제출 핸들러
  const handleSubmit = (e) => {
    e.preventDefault();
    onStartGeneration({
      selectedFields,
      includeSource,
    });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* 타이틀 영역 */}
      <div>
        <h2 className="text-2xl font-extrabold text-gray-900 tracking-tight">MARC 생성 - 옵션 설정</h2>
        <p className="text-gray-500 text-sm font-semibold mt-1">생성할 필드를 선택해주세요</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        
        {/* 1. 필수 필드 박스 */}
        <div className="bg-white border border-gray-300 rounded-xl p-6 space-y-4 shadow-sm">
          <h3 className="text-base font-extrabold text-gray-900">필수 필드</h3>
          <div className="space-y-3">
            <label className="flex items-center space-x-3 cursor-not-allowed select-none text-gray-900 font-bold text-xs">
              <input 
                type="checkbox" 
                checked 
                disabled 
                className="w-4 h-4 accent-black rounded border-gray-400 bg-black text-white" 
              />
              <span>제목 (245)</span>
            </label>
            <label className="flex items-center space-x-3 cursor-not-allowed select-none text-gray-900 font-bold text-xs">
              <input 
                type="checkbox" 
                checked 
                disabled 
                className="w-4 h-4 accent-black rounded border-gray-400 bg-black text-white" 
              />
              <span>ISBN (020)</span>
            </label>
            <label className="flex items-center space-x-3 cursor-not-allowed select-none text-gray-900 font-bold text-xs">
              <input 
                type="checkbox" 
                checked 
                disabled 
                className="w-4 h-4 accent-black rounded border-gray-400 bg-black text-white" 
              />
              <span>자료유형 (008)</span>
            </label>
          </div>
        </div>

        {/* 2. 선택 필드 박스 */}
        <div className="bg-white border border-gray-300 rounded-xl p-6 space-y-4 shadow-sm">
          <h3 className="text-base font-extrabold text-gray-900">선택 필드</h3>
          <div className="space-y-3">
            <label className="flex items-center space-x-3 cursor-pointer select-none text-gray-900 font-bold text-xs">
              <input 
                type="checkbox" 
                checked={selectedFields.author} 
                onChange={() => handleCheckboxChange('author')} 
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500" 
              />
              <span>저자 (100, 700)</span>
            </label>
            <label className="flex items-center space-x-3 cursor-pointer select-none text-gray-900 font-bold text-xs">
              <input 
                type="checkbox" 
                checked={selectedFields.publisher} 
                onChange={() => handleCheckboxChange('publisher')} 
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500" 
              />
              <span>출판사 (222)</span>
            </label>
            <label className="flex items-center space-x-3 cursor-pointer select-none text-gray-900 font-bold text-xs">
              <input 
                type="checkbox" 
                checked={selectedFields.subject} 
                onChange={() => handleCheckboxChange('subject')} 
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500" 
              />
              <span>주제명 (999)</span>
            </label>
          </div>
        </div>

        {/* 3. 출처 표시 포함 박스 */}
        <div className="bg-white border border-gray-300 rounded-xl p-6 shadow-sm">
          <label className="flex items-start space-x-3 cursor-pointer select-none text-gray-900 text-xs">
            <input 
              type="checkbox" 
              checked={includeSource} 
              onChange={() => setIncludeSource(!includeSource)} 
              className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 mt-0.5" 
            />
            <div>
              <span className="font-extrabold text-gray-900 block text-sm">출처 표시 포함</span>
              <span className="text-gray-400 font-semibold mt-1 block">생성된 필드의 출처 정보를 함께 저장</span>
            </div>
          </label>
        </div>

        {/* 하단 버튼 영역 */}
        <div className="flex items-center justify-between pt-4 border-t border-gray-100">
          <button
            type="button"
            onClick={onPrev}
            className="px-6 py-2.5 border border-gray-300 text-gray-700 font-bold text-xs rounded-xl hover:bg-gray-100 transition bg-white"
          >
            취소
          </button>
          <button
            type="submit"
            className="px-6 py-2.5 font-bold text-xs rounded-xl transition-all bg-gray-800 text-white hover:bg-black shadow-sm"
          >
            다음 단계
          </button>
        </div>

      </form>
    </div>
  );
}