import React, { useState, useEffect } from 'react';

export default function MARCInput({ initialTab, onNextStep, onCancel }) {
  // 홈 대시보드에서 클릭한 카드 종류(single, multiple, manual)를 초기 탭으로 설정
  const [activeTab, setActiveTab] = useState(initialTab || 'single');

  // --- 입력 폼 데이터 상태 관리 ---
  const [singleIsbn, setSingleIsbn] = useState('');
  const [singleValidationMsg, setSingleValidationMsg] = useState('');
  const [isIsbnValid, setIsIsbnValid] = useState(null); 

  const [multipleIsbn, setMultipleIsbn] = useState('');
  const [manualForm, setManualForm] = useState({ title: '', author: '', publisher: '', year: '' });

  // --- [단일 ISBN] 실시간 검증 ---
  useEffect(() => {
    if (!singleIsbn) {
      setSingleValidationMsg('');
      setIsIsbnValid(null);
      return;
    }
    const cleanIsbn = singleIsbn.replace(/[- ]/g, '');
    if (cleanIsbn.length === 10 || cleanIsbn.length === 13) {
      if (/^\d+$/.test(cleanIsbn)) {
        setSingleValidationMsg('✓ 유효한 ISBN입니다 (10 or 13자리 입력 경우)');
        setIsIsbnValid(true); 
      } else {
        setSingleValidationMsg('✕ 유효하지 않은 ISBN입니다');
        setIsIsbnValid(false);
      }
    } else {
      setSingleValidationMsg('✕ 유효하지 않은 ISBN입니다');
      setIsIsbnValid(false);
    }
  }, [singleIsbn]);

  // 하단 '다음 단계' 활성화 조건판정
  const isNextDisabled = () => {
    if (activeTab === 'single') return !isIsbnValid;
    if (activeTab === 'multiple') return !multipleIsbn.trim();
    if (activeTab === 'manual') return !manualForm.title.trim() || !manualForm.author.trim();
    return true;
  };

  // [취소] 버튼 클릭 시 입력값 초기화 및 홈으로 복귀
  const handleCancelInput = () => {
    if (activeTab === 'single') {
      setSingleIsbn('');
    } else if (activeTab === 'multiple') {
      setMultipleIsbn('');
    } else if (activeTab === 'manual') {
      setManualForm({ title: '', author: '', publisher: '', year: '' });
    }
    if (onCancel) onCancel(); // 홈 화면으로 이동 트리거
  };

  // 다음 단계 폼 제출 핸들러
  const handleSubmit = (e) => {
    e.preventDefault();
    if (onNextStep) onNextStep();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-xl font-extrabold text-gray-900 tracking-tight">MARC 생성 - 입력</h2>
        <p className="text-gray-400 text-xs font-semibold mt-0.5">도서 정보를 입력해주세요</p>
      </div>

      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        {/* 상단 탭 선택 바 */}
        <div className="flex border-b border-gray-200 bg-white px-6">
          <button type="button" onClick={() => setActiveTab('single')} className={`py-4 px-6 font-bold text-xs border-b-2 transition-colors ${activeTab === 'single' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'}`}>
            단일 ISBN
          </button>
          <button type="button" onClick={() => setActiveTab('multiple')} className={`py-4 px-6 font-bold text-xs border-b-2 transition-colors ${activeTab === 'multiple' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'}`}>
            복수 ISBN
          </button>
          <button type="button" onClick={() => setActiveTab('manual')} className={`py-4 px-6 font-bold text-xs border-b-2 transition-colors ${activeTab === 'manual' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'}`}>
            수기 입력
          </button>
        </div>

        <div className="p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            
            {/* 단일 ISBN 입력 뷰 */}
            {activeTab === 'single' && (
              <div className="space-y-2 min-h-[140px]">
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">ISBN</label>
                <input
                  type="text"
                  value={singleIsbn}
                  onChange={(e) => setSingleIsbn(e.target.value)}
                  placeholder="9788901234567 (10자리 또는 13자리)"
                  className="w-full px-4 py-3.5 border border-gray-200 rounded-xl bg-gray-50/50 text-sm focus:outline-none focus:bg-white focus:border-gray-400 transition"
                />
                {singleIsbn && (
                  <p className={`text-xs font-bold pt-1 ${isIsbnValid ? 'text-green-600' : 'text-red-500'}`}>
                    {singleValidationMsg}
                  </p>
                )}
              </div>
            )}

            {/* 복수 ISBN 입력 뷰 */}
            {activeTab === 'multiple' && (
              <div className="space-y-2 min-h-[140px]">
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">복수 ISBN (줄바꿈 또는 쉼표로 구분)</label>
                <textarea
                  rows="4"
                  value={multipleIsbn}
                  onChange={(e) => setMultipleIsbn(e.target.value)}
                  placeholder="9788901234567&#10;9788901234566"
                  className="w-full px-4 py-3.5 border border-gray-200 rounded-xl bg-gray-50/50 text-sm font-mono focus:outline-none focus:bg-white focus:border-gray-400 transition"
                />
              </div>
            )}

            {/* 수기 직접 입력 뷰 */}
            {activeTab === 'manual' && (
              <div className="space-y-4 min-h-[140px]">
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-gray-700">제목 *</label>
                  <input type="text" value={manualForm.title} onChange={(e) => setManualForm({ ...manualForm, title: e.target.value })} placeholder="도서 제목" className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-gray-400" />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-gray-700">저자 *</label>
                  <input type="text" value={manualForm.author} onChange={(e) => setManualForm({ ...manualForm, author: e.target.value })} placeholder="저자명" className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-gray-400" />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-gray-700">출판사</label>
                  <input type="text" value={manualForm.publisher} onChange={(e) => setManualForm({ ...manualForm, publisher: e.target.value })} placeholder="출판사명" className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-gray-400" />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-gray-700">출판연도</label>
                  <input type="text" value={manualForm.year} onChange={(e) => setManualForm({ ...manualForm, year: e.target.value })} placeholder="2026" className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-gray-400" />
                </div>
              </div>
            )}

            {/* 하단 제어 버튼단 */}
            <div className="flex items-center justify-between pt-4 border-t border-gray-100">
              <button type="button" onClick={handleCancelInput} className="px-6 py-2.5 border border-gray-300 text-gray-700 font-bold text-xs rounded-xl hover:bg-gray-100 transition">
                취소
              </button>
              <button type="submit" disabled={isNextDisabled()} className={`px-6 py-2.5 font-bold text-xs rounded-xl transition-all ${isNextDisabled() ? 'bg-gray-300 text-gray-100 cursor-not-allowed' : 'bg-gray-800 text-white hover:bg-black shadow-sm'}`}>
                다음 단계
              </button>
            </div>

          </form>
        </div>
      </div>
    </div>
  );
}