import React, { useEffect, useState } from 'react';
import { generateMarcByIsbn } from '../../api/marc';

// ISBN 유효성 검사 함수
function isValidIsbn(value) {
  const clean = value.replace(/[-\s]/g, '').toUpperCase();
  if (clean.length === 10) return /^\d{9}[\dX]$/.test(clean);
  if (clean.length === 13) return /^\d{13}$/.test(clean);
  return false;
}

// [MOCK DATA 시작] 백엔드 미연결 시 UI 테스트용 더미 생성 함수 (삭제 필요)
function createMockMarcResult(isbn, title) {
  return {
    leader: "00000nam a2200000 a 4500",
    fields: [
      { tag: "020", ind1: " ", ind2: " ", subfields: { a: isbn }, review_required: false },
      { tag: "200", ind1: "1", ind2: " ", subfields: { a: title || `도서 (ISBN: ${isbn})`, f: "저자 미상" }, review_required: false },
      { tag: "260", ind1: " ", ind2: " ", subfields: { a: "서울", b: "가상출판사", c: "2026" }, review_required: true },
    ]
  };
}
// [MOCK DATA 끝]

export default function MARCInput({ initialTab, onGenerated, onCancel }) {
  const [activeTab, setActiveTab] = useState(initialTab || 'single');
  const [singleIsbn, setSingleIsbn] = useState('');
  const [singleValidationMsg, setSingleValidationMsg] = useState('');
  const [isIsbnValid, setIsIsbnValid] = useState(null);

  const [multipleIsbn, setMultipleIsbn] = useState('');
  const [validIsbns, setValidIsbns] = useState([]);
  const [invalidIsbns, setInvalidIsbns] = useState([]);

  const [manualForm, setManualForm] = useState({ title: '', author: '', publisher: '', year: '' });
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // 단일 ISBN 유효성 검사
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

  // 복수 ISBN 입력 시 줄바꿈/쉼표로 분리하여 추출
  useEffect(() => {
    if (!multipleIsbn.trim()) {
      setValidIsbns([]);
      setInvalidIsbns([]);
      return;
    }

    const lines = multipleIsbn
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter((item) => item.length > 0);

    const valid = lines.filter((isbn) => isValidIsbn(isbn));
    const invalid = lines.filter((isbn) => !isValidIsbn(isbn));

    setValidIsbns(valid);
    setInvalidIsbns(invalid);
  }, [multipleIsbn]);

  // 생성 버튼 활성화 조건 판별
  const isNextDisabled = () => {
    if (isGenerating) return true;
    if (activeTab === 'single') return !isIsbnValid;
    if (activeTab === 'multiple') return validIsbns.length === 0 && invalidIsbns.length === 0;
    if (activeTab === 'manual') return !manualForm.title.trim();
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
    if (isNextDisabled()) return;

    setIsGenerating(true);
    setErrorMessage('');

    try {
      // 1. 단일 ISBN 처리
      if (activeTab === 'single') {
        const trimmed = singleIsbn.trim();
        let result;
        try {
          // 백엔드 호출 시도
          result = await generateMarcByIsbn(trimmed);
        } catch {
          // [MOCK DATA 시작] 백엔드 미연결 시 전용 처리 (삭제 필요)
          result = createMockMarcResult(trimmed, `단일 조회 도서 (${trimmed})`);
          // [MOCK DATA 끝]
        }

        onGenerated?.([{
          id: Date.now(),
          isbn: trimmed,
          title: result.fields?.find(f => f.tag === '200')?.subfields?.a || `도서 (${trimmed})`,
          status: result.fields?.some((field) => field.review_required) ? '검수 필요' : '완료',
          result,
        }]);
      }
      // 2. 복수 ISBN 처리 (다건 입력)
      else if (activeTab === 'multiple') {
        const results = [];

        // 1) 형식이 잘못된 ISBN 처리 (조회 실패 분류)
        invalidIsbns.forEach((isbn, idx) => {
          results.push({
            id: Date.now() + idx,
            isbn,
            title: '도서 정보를 찾을 수 없음',
            status: '조회 실패',
            error: 'ISBN 규격 불일치 (10자리 또는 13자리 필요)',
            result: null,
          });
        });

        // 2) 유효한 ISBN 처리 
        for (let i = 0; i < validIsbns.length; i++) {
          const isbn = validIsbns[i];
          let result;
          try {
            result = await generateMarcByIsbn(isbn);
          } catch (error) {
            // [MOCK DATA 시작] 백엔드 미연결 시 전용 처리 (삭제 필요)
            result = createMockMarcResult(isbn, `테스트 도서 ${i + 1} (${isbn})`);
            // [MOCK DATA 끝]
          }

          results.push({
            id: Date.now() + invalidIsbns.length + i,
            isbn,
            title: result.fields?.find(f => f.tag === '200')?.subfields?.a || `테스트 도서 ${i + 1}`,
            status: result.fields?.some((field) => field.review_required) ? '검수 필요' : '완료',
            result,
          });
        }

        onGenerated?.(results);
      }
      // 3. 직접 입력 처리
      else if (activeTab === 'manual') {
        // [MOCK DATA 시작] 백엔드 API 미존재로 가짜 데이터 반환 (삭제 필요)
        const result = createMockMarcResult("직접 입력", manualForm.title);
        // [MOCK DATA 끝]
        onGenerated?.([{
          id: Date.now(),
          isbn: '직접 입력',
          title: manualForm.title,
          status: '검수 필요',
          result,
        }]);
      }
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
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">복수 ISBN (줄바꿈 또는 쉼표로 구분)</label>
                <textarea
                  rows="5"
                  value={multipleIsbn}
                  onChange={(event) => setMultipleIsbn(event.target.value)}
                  placeholder={`9788936434595\n9788936434596\n9788936434597`}
                  className="w-full px-4 py-3.5 border border-gray-200 rounded-xl bg-gray-50/50 text-sm font-mono focus:outline-none focus:bg-white focus:border-gray-400 transition"
                />
                {multipleIsbn.trim() && (
                  <div className="flex items-center gap-4 text-xs font-bold pt-1">
                    <span className="text-green-600">유효한 ISBN: {validIsbns.length}개</span>
                    {invalidIsbns.length > 0 && (
                      <span className="text-red-500">형식 오류: {invalidIsbns.length}개 (조회 실패 처리)</span>
                    )}
                  </div>
                )}
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
