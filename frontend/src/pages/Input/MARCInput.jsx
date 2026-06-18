import React, { useEffect, useState } from 'react';
import { generateMarcByIsbn } from '../../api/marc';

function isValidIsbn(value) {
  const clean = value.replace(/[-\s]/g, '').toUpperCase();
  if (clean.length === 10) return /^\d{9}[\dX]$/.test(clean);
  if (clean.length === 13) return /^\d{13}$/.test(clean);
  return false;
}

export default function MARCInput({ initialTab, onGenerated, onCancel }) {
  const [activeTab, setActiveTab] = useState(initialTab || 'single');
  const [singleIsbn, setSingleIsbn] = useState('');
  const [singleValidationMsg, setSingleValidationMsg] = useState('');
  const [isIsbnValid, setIsIsbnValid] = useState(null);
  const [multipleIsbn, setMultipleIsbn] = useState('');
  const [manualForm, setManualForm] = useState({ title: '', author: '', publisher: '', year: '' });
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    if (!singleIsbn) {
      setSingleValidationMsg('');
      setIsIsbnValid(null);
      return;
    }

    if (isValidIsbn(singleIsbn)) {
      setSingleValidationMsg('유효한 ISBN 형식입니다.');
      setIsIsbnValid(true);
    } else {
      setSingleValidationMsg('ISBN은 10자리 또는 13자리 형식으로 입력해 주세요.');
      setIsIsbnValid(false);
    }
  }, [singleIsbn]);

  const isNextDisabled = () => {
    if (isGenerating) return true;
    if (activeTab === 'single') return !isIsbnValid;
    if (activeTab === 'multiple') return true;
    if (activeTab === 'manual') return true;
    return true;
  };

  const handleCancelInput = () => {
    setSingleIsbn('');
    setMultipleIsbn('');
    setManualForm({ title: '', author: '', publisher: '', year: '' });
    setErrorMessage('');
    if (onCancel) onCancel();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (activeTab !== 'single' || !isIsbnValid) return;

    setIsGenerating(true);
    setErrorMessage('');

    try {
      const result = await generateMarcByIsbn(singleIsbn.trim());
      onGenerated?.({
        id: Date.now(),
        isbn: singleIsbn.trim(),
        status: result.fields?.some((field) => field.review_required) ? '검수 필요' : '완료',
        result,
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-xl font-extrabold text-gray-900 tracking-tight">MARC 생성</h2>
        <p className="text-gray-500 text-sm font-semibold mt-1">ISBN을 입력하면 서지 조회와 LLM 생성을 한 번에 실행합니다.</p>
      </div>

      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-200 bg-white px-6">
          <button type="button" onClick={() => setActiveTab('single')} className={`py-4 px-6 font-bold text-xs border-b-2 transition-colors ${activeTab === 'single' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'}`}>
            단일 ISBN
          </button>
          <button type="button" onClick={() => setActiveTab('multiple')} className={`py-4 px-6 font-bold text-xs border-b-2 transition-colors ${activeTab === 'multiple' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'}`}>
            복수 ISBN
          </button>
          <button type="button" onClick={() => setActiveTab('manual')} className={`py-4 px-6 font-bold text-xs border-b-2 transition-colors ${activeTab === 'manual' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'}`}>
            직접 입력
          </button>
        </div>

        <div className="p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {activeTab === 'single' && (
              <div className="space-y-2 min-h-[150px]">
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">ISBN</label>
                <input
                  type="text"
                  value={singleIsbn}
                  onChange={(event) => setSingleIsbn(event.target.value)}
                  placeholder="예: 9788936434595"
                  className="w-full px-4 py-3.5 border border-gray-200 rounded-xl bg-gray-50/50 text-sm font-mono focus:outline-none focus:bg-white focus:border-gray-400 transition"
                />
                {singleIsbn && (
                  <p className={`text-xs font-bold pt-1 ${isIsbnValid ? 'text-green-600' : 'text-red-500'}`}>
                    {singleValidationMsg}
                  </p>
                )}
                <p className="text-xs text-gray-400 font-medium">
                  백엔드 서버가 켜져 있고 `backend/.env`에 API 키가 있어야 LLM 생성이 완료됩니다.
                </p>
              </div>
            )}

            {activeTab === 'multiple' && (
              <div className="space-y-2 min-h-[150px]">
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">복수 ISBN</label>
                <textarea
                  rows="4"
                  value={multipleIsbn}
                  onChange={(event) => setMultipleIsbn(event.target.value)}
                  placeholder="아직 실제 LLM 호출은 단일 ISBN만 연결되어 있습니다."
                  className="w-full px-4 py-3.5 border border-gray-200 rounded-xl bg-gray-50/50 text-sm font-mono focus:outline-none focus:bg-white focus:border-gray-400 transition"
                />
              </div>
            )}

            {activeTab === 'manual' && (
              <div className="space-y-4 min-h-[150px]">
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-gray-700">제목</label>
                  <input type="text" value={manualForm.title} onChange={(event) => setManualForm({ ...manualForm, title: event.target.value })} placeholder="도서 제목" className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-gray-400" />
                </div>
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold text-gray-700">저자</label>
                  <input type="text" value={manualForm.author} onChange={(event) => setManualForm({ ...manualForm, author: event.target.value })} placeholder="저자명" className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-gray-400" />
                </div>
                <p className="text-xs text-gray-400 font-medium">직접 입력 생성은 아직 백엔드 API가 없어 비활성화되어 있습니다.</p>
              </div>
            )}

            {errorMessage && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 whitespace-pre-wrap">
                {errorMessage}
              </div>
            )}

            <div className="flex items-center justify-between pt-4 border-t border-gray-100">
              <button type="button" onClick={handleCancelInput} className="px-6 py-2.5 border border-gray-300 text-gray-700 font-bold text-xs rounded-xl hover:bg-gray-100 transition">
                취소
              </button>
              <button type="submit" disabled={isNextDisabled()} className={`px-6 py-2.5 font-bold text-xs rounded-xl transition-all ${isNextDisabled() ? 'bg-gray-300 text-gray-100 cursor-not-allowed' : 'bg-gray-800 text-white hover:bg-black shadow-sm'}`}>
                {isGenerating ? 'LLM 생성 중...' : 'MARC 생성'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
