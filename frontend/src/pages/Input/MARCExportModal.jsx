import React, { useState } from 'react';

export default function MARCExportModal({ onClose }) {
  // 1. 내보내기 단계 상태 관리 (1: 형식 선택, 2: 미리보기 및 다운로드)
  const [step, setStep] = useState(1);
  
  // 2. 내보내기 형식 라디오 버튼 상태 관리
  const [exportFormat, setExportFormat] = useState('marc');

  // KORMARC 텍스트 더미 데이터 샘플
  const simulatedMarcRaw = 
`00000nam a2200241   4500
001 AI-GENERATED-20260514-003
005 20260514114522.0
020   $a9788901234569$c₩18000
100 1 $a홍길동
245 10$a대시보드와 데이터 시각화 개론 :$b실무 가이드 /$c홍길동 지음
260   $a서울 :$b테크출판사,$c2026
300   $a254 p. :$b삽도 ;$c24 cm`;

  // 클립보드 복사 핸들러
  const handleCopyToClipboard = () => {
    navigator.clipboard.writeText(simulatedMarcRaw);
    alert('MARC 텍스트가 클립보드에 복사되었습니다! 도서관 시스템에 붙여넣을 수 있습니다.');
  };

  // 파일 다운로드 핸들러
  const handleDownloadFile = () => {
    const element = document.createElement("a");
    const file = new Blob([simulatedMarcRaw], {type: 'text/plain'});
    element.href = URL.createObjectURL(file);
    element.download = `KORMARC_EXPORT_${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(element);
    element.click();
    alert('KORMARC txt 파일 다운로드가 시작되었습니다.');
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
      <div className="bg-white border border-gray-300 rounded-2xl p-6 w-full max-w-lg shadow-xl space-y-6 relative">

        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 text-lg font-bold transition-colors p-1"
          title="닫기"
        >
          ✕
        </button>
        
        {/* STEP 1: 내보내기 형식 선택 화면 */}
        {step === 1 && (
          <>
            <div>
              <h3 className="text-xl font-extrabold text-gray-900 tracking-tight">내보내기</h3>
              <p className="text-gray-500 text-xs font-bold mt-1">원하는 내보내기 형식을 선택해주세요</p>
            </div>

            <div className="space-y-3">
              <label className={`flex items-center space-x-3 p-4 border rounded-xl cursor-pointer transition select-none ${exportFormat === 'marc' ? 'border-blue-600 bg-blue-50/10 ring-1 ring-blue-600' : 'border-gray-200 hover:border-gray-300'}`}>
                <input 
                  type="radio" 
                  name="format" 
                  checked={exportFormat === 'marc'} 
                  onChange={() => setExportFormat('marc')}
                  className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                />
                <div>
                  <span className="text-xs font-bold text-gray-900 block">MARC 텍스트 (.txt)</span>
                  <span className="text-gray-400 text-[10px] font-semibold block mt-0.5">실제 도서관 시스템 반입용 표준 텍스트 파일</span>
                </div>
              </label>

              <label className={`flex items-center space-x-3 p-4 border rounded-xl cursor-pointer transition select-none ${exportFormat === 'las' ? 'border-blue-600 bg-blue-50/10 ring-1 ring-blue-600' : 'border-gray-200 hover:border-gray-300'}`}>
                <input 
                  type="radio" 
                  name="format" 
                  checked={exportFormat === 'las'} 
                  onChange={() => setExportFormat('las')}
                  className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                />
                <div>
                  <span className="text-xs font-bold text-gray-900 block">LAS / K-LAS 복사용</span>
                  <span className="text-gray-400 text-[10px] font-semibold block mt-0.5">클립보드에 복사하여 학사관리시스템에 바로 붙여넣기</span>
                </div>
              </label>

              <label className={`flex items-center space-x-3 p-4 border rounded-xl cursor-pointer transition select-none ${exportFormat === 'excel' ? 'border-blue-600 bg-blue-50/10 ring-1 ring-blue-600' : 'border-gray-200 hover:border-gray-300'}`}>
                <input 
                  type="radio" 
                  name="format" 
                  checked={exportFormat === 'excel'} 
                  onChange={() => setExportFormat('excel')}
                  className="w-4 h-4 text-blue-600 border-gray-300 focus:ring-blue-500"
                />
                <div>
                  <span className="text-xs font-bold text-gray-900 block">Excel / 세부 목록 (.xlsx)</span>
                  <span className="text-gray-400 text-[10px] font-semibold block mt-0.5">도서 목록 백업 및 보관, 정리용 엑셀 데이터 파일</span>
                </div>
              </label>
            </div>

            {/* 하단 제어 단추 */}
            <div className="flex items-center justify-between pt-4 border-t border-gray-100">
              <button
                type="button"
                onClick={onClose}
                className="px-6 py-2.5 border border-gray-300 text-gray-700 font-bold text-xs rounded-xl hover:bg-gray-100 transition bg-white"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => setStep(2)}
                className="px-6 py-2.5 bg-gray-800 text-white font-bold text-xs rounded-xl hover:bg-black shadow-sm"
              >
                다음 단계
              </button>
            </div>
          </>
        )}

        {/* STEP 2: 내보내기 상세 파일 미리보기 및 완료 화면 */}
        {step === 2 && (
          <>
            <div>
              <h3 className="text-xl font-extrabold text-gray-900 tracking-tight">내보내기 - 미리보기</h3>
              <p className="text-gray-500 text-xs font-bold mt-1">선택한 형식으로 정제된 KORMARC 표준 데이터 내역입니다.</p>
            </div>

            {/* 정갈한 데이터 프리뷰 박스 */}
            <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 max-h-60 overflow-y-auto font-mono text-[11px] text-gray-700 leading-relaxed whitespace-pre-wrap">
              {simulatedMarcRaw}
            </div>

            {/* 하단 제어 단추 */}
            <div className="flex items-center justify-between pt-4 border-t border-gray-100">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="px-6 py-2.5 border border-gray-300 text-gray-700 font-bold text-xs rounded-xl hover:bg-gray-100 transition bg-white"
              >
                이전
              </button>
              <div className="flex space-x-2">
                <button
                  type="button"
                  onClick={handleCopyToClipboard}
                  className="px-4 py-2.5 border border-gray-300 text-gray-800 font-bold text-xs rounded-xl hover:bg-gray-100 transition bg-white"
                >
                  텍스트 복사
                </button>
                <button
                  type="button"
                  onClick={handleDownloadFile}
                  className="px-5 py-2.5 bg-blue-700 text-white font-bold text-xs rounded-xl hover:bg-blue-800 shadow-sm"
                >
                  다운로드
                </button>
              </div>
            </div>
          </>
        )}

      </div>
    </div>
  );
}