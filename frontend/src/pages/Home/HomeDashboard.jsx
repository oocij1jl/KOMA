import React, { useState } from 'react';

// 페이지별 분리된 하위 컴포넌트 임포트 
import MARCInput from '../Input/MARCInput';
import MARCOptions from '../Input/MARCOptions';
import MARCProgress from '../Input/MARCProgress';
import MARCResultList from '../Input/MARCResultList';
import MARCInspection from '../Input/MARCInspection';
import MARCHistory from '../History/MARCHistory';
import MARCSettings from '../Settings/MARCSettings';

const StatusBadge = ({ status }) => {
  const styles = {
    완료: 'bg-green-100 text-green-800 border-green-200',
    생성중: 'bg-blue-100 text-blue-800 border-blue-200 animate-pulse',
    실패: 'bg-red-100 text-red-800 border-red-200',
  };
  return (
    <span className={`px-2 py-1 text-xs font-semibold border rounded-full ${styles[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  );
};

export default function HomeDashboard() {
  // --- 글로벌 라우터 상태 관리 ---
  const [currentView, setCurrentView] = useState('home'); 
  const [activeInputTab, setActiveInputTab] = useState('single');
  const [selectedBook, setSelectedBook] = useState(null);

  // 최근 생성 이력 데이터 셋 (더미데이터)
  const [recentHistory] = useState([
    { id: 1, date: '2026-05-14', taskName: '작업 #3', count: 5, status: '완료' },
    { id: 2, date: '2026-05-14', taskName: '작업 #2', count: 1, status: '완료' },
    { id: 3, date: '2026-05-14', taskName: '작업 #1', count: 3, status: '생성중' },
    { id: 4, date: '2026-05-13', taskName: '작업 #0', count: 2, status: '실패' },
  ]);

  // 홈에서 새 생성 바로가기 카드 누를 시 구동
  const handleInputMethodJump = (methodType) => {
    setActiveInputTab(methodType);
    setCurrentView('input');
  };

  // 최근 이력 카드 클릭 제어 핸들러
  const handleSelectHistoryTask = (task) => {
    if (task.status === '생성중') {
      setCurrentView('loading');
    } else if (task.status !== '실패') {
      setCurrentView('results');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans antialiased">
      
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-2 cursor-pointer" onClick={() => setCurrentView('home')}>
            <span className="text-2xl font-extrabold text-gray-900 tracking-tight">KOMA</span>
          </div>
          <nav className="flex space-x-10 font-bold text-gray-500 text-sm">
            <button 
              onClick={() => setCurrentView('home')} 
              className={`pb-5 pt-5 transition-all border-b-2 ${currentView === 'home' ? 'text-blue-600 border-blue-600' : 'border-transparent hover:text-blue-600'}`}
            >
              홈
            </button>
            <button 
              onClick={() => setCurrentView('history')} 
              className={`pb-5 pt-5 transition-all border-b-2 ${currentView === 'history' ? 'text-blue-600 border-blue-600' : 'border-transparent hover:text-blue-600'}`}
            >
              이력
            </button>
            <button 
              onClick={() => setCurrentView('settings')} 
              className={`pb-5 pt-5 transition-all border-b-2 ${currentView === 'settings' ? 'text-blue-600 border-blue-600' : 'border-transparent hover:text-blue-600'}`}
            >
              설정
            </button>
          </nav>
        </div>
      </header>

      {/* 중앙 메인 본문 영역 */}
      <div className="max-w-6xl mx-auto px-6 py-10">
        
      {/* VIEW 1 */}
        {currentView === 'home' && (
          <div className="space-y-12">

            <section className="text-center bg-white border border-gray-200 rounded-3xl p-12 shadow-sm">
              <h1 className="text-3xl font-extrabold text-gray-900 mb-3 tracking-tight">
                KORMARC 레코드 자동 생성 서비스
              </h1>
              <p className="text-gray-400 text-base mb-8 max-w-xl mx-auto font-medium">
                ISBN 또는 서지정보를 입력하여 MARC 레코드를 빠르게 생성하세요.
              </p>
              <button
                onClick={() => handleInputMethodJump('single')}
                className="bg-black hover:bg-gray-800 text-white font-bold text-sm px-10 py-4 rounded-full transition-all tracking-wide"
              >
                새 MARC 생성하기
              </button>
            </section>

            {/* 최근 생성 이력 */}
            <section>
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-extrabold text-gray-900 tracking-tight">최근 생성 이력</h2>
                <button onClick={() => setCurrentView('history')} className="text-xs text-blue-600 font-bold hover:underline">전체 보기</button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {recentHistory.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleSelectHistoryTask(item)}
                    className="bg-white border border-gray-200 rounded-2xl p-5 shadow-sm hover:border-gray-400 cursor-pointer transition flex flex-col justify-between min-h-[140px]"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-gray-400">{item.date}</span>
                        <StatusBadge status={item.status} />
                      </div>
                      <h3 className="font-extrabold text-base text-gray-800">{item.taskName}</h3>
                    </div>
                    <div className="text-xs text-gray-400 font-medium">{item.count} 건 생성됨</div>
                  </div>
                ))}
              </div>
            </section>

            {/* 하단 원본 카드 영역 */}
            <section className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div onClick={() => handleInputMethodJump('single')} className="bg-white p-6 border border-gray-200 rounded-2xl cursor-pointer hover:border-gray-400 transition---">
                <div className="text-xl mb-3">📄</div>
                <h4 className="font-extrabold text-sm text-gray-900 mb-1">단일 ISBN 입력</h4>
                <p className="text-gray-400 text-xs leading-relaxed font-medium">한 건의 도서 ISBN을 입력하여 MARC 레코드를 생성합니다.</p>
              </div>
              <div onClick={() => handleInputMethodJump('multiple')} className="bg-white p-6 border border-gray-200 rounded-2xl cursor-pointer hover:border-gray-400 transition---">
                <div className="text-xl mb-3">📚</div>
                <h4 className="font-extrabold text-sm text-gray-900 mb-1">복수 ISBN 입력</h4>
                <p className="text-gray-400 text-xs leading-relaxed font-medium">여러 건의 ISBN을 입력하여 일괄적으로 MARC 레코드를 자동 빌드합니다.</p>
              </div>
              <div onClick={() => handleInputMethodJump('manual')} className="bg-white p-6 border border-gray-200 rounded-2xl cursor-pointer hover:border-gray-400 transition---">
                <div className="text-xl mb-3">✍️</div>
                <h4 className="font-extrabold text-sm text-gray-900 mb-1">수기 서지정보 직접 입력</h4>
                <p className="text-gray-400 text-xs leading-relaxed font-medium">ISBN이 없는 도서의 서지정보를 직접 쳐서 인덱싱 데이터를 유도합니다.</p>
              </div>
            </section>
          </div>
        )}

        {/* VIEW 2: MARC 생성 - 순수 입력 창 */}
        {currentView === 'input' && (
          <MARCInput 
            initialTab={activeInputTab}
            onNextStep={() => setCurrentView('options')}
            onCancel={() => setCurrentView('home')}
          />
        )}

        {/* VIEW 3: 옵션 필드 체킹 보드 */}
        {currentView === 'options' && (
          <MARCOptions 
            onPrev={() => setCurrentView('input')} 
            onStartGeneration={() => setCurrentView('loading')} 
          />
        )}

        {/* VIEW 4: 생성 프로그레스 진행 상황 */}
        {currentView === 'loading' && (
          <MARCProgress 
            onCancel={() => {
              if (window.confirm("MARC 생성을 중단하고 이전 단계로 돌아가시겠습니까?")) {
                setCurrentView('options');
              }
            }}
            onComplete={() => setCurrentView('results')} 
          />
        )}

        {/* VIEW 5: 생성 결과 리스트 테이블 */}
        {currentView === 'results' && (
          <MARCResultList 
            onSelectDetail={(book) => {
              setSelectedBook(book);
              setCurrentView('inspect');
            }} 
          />
        )}

        {/* VIEW 6: 상세 검수 인라인 테이블 */}
        {currentView === 'inspect' && (
          <MARCInspection 
            selectedBook={selectedBook} 
            onBackToList={() => setCurrentView('results')} 
          />
        )}

        {/* VIEW 7: 누적 생성 이력 카드 대시보드 */}
        {currentView === 'history' && (
          <MARCHistory 
            onSelectTask={(task) => {
              if (task.status === '생성중') setCurrentView('loading');
              else setCurrentView('results');
            }} 
          />
        )}

        {/* VIEW 8: 시스템 설정 및 스토리지 패널 */}
        {currentView === 'settings' && (
          <MARCSettings />
        )}

      </div>
    </div>
  );
}