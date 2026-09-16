import React, { useState } from 'react';

import MARCInput from '../Input/MARCInput';
import MARCResultList from '../Input/MARCResultList';
import MARCInspection from '../Input/MARCInspection';
import MARCHistory from '../History/MARCHistory';
import MARCSettings from '../Settings/MARCSettings';

const StatusBadge = ({ status }) => {
  const styles = {
    완료: 'bg-green-100 text-green-800 border-green-200',
    '검수 필요': 'bg-amber-100 text-amber-800 border-amber-200',
    실패: 'bg-red-100 text-red-800 border-red-200',
  };

  return (
    <span className={`px-2 py-1 text-xs font-semibold border rounded-full ${styles[status] || 'bg-gray-100 text-gray-700 border-gray-200'}`}>
      {status}
    </span>
  );
};

function getTitleFromResult(result) {
  const titleField = result?.fields?.find((field) => field.tag === '245');
  const titleSubfield = titleField?.subfields?.find((subfield) => subfield.code === 'a');
  return titleSubfield?.value || '제목 미확인';
}

export default function HomeDashboard() {
  const [currentView, setCurrentView] = useState('home');
  const [activeInputTab, setActiveInputTab] = useState('single');
  const [selectedBook, setSelectedBook] = useState(null);
  const [generatedResults, setGeneratedResults] = useState([]);

  const recentHistory = generatedResults.slice(0, 4);

  const handleInputMethodJump = (methodType) => {
    setActiveInputTab(methodType);
    setCurrentView('input');
  };

  const handleGenerated = (generatedItem) => {
    const item = {
      ...generatedItem,
      title: getTitleFromResult(generatedItem.result),
      fields: generatedItem.result?.fields?.length ?? 0,
      createdAt: new Date().toLocaleString('ko-KR'),
    };

    setGeneratedResults((previous) => [item, ...previous]);
    setSelectedBook(item);
    setCurrentView('inspect');
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans antialiased">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-2 cursor-pointer" onClick={() => setCurrentView('home')}>
            <span className="text-2xl font-extrabold text-gray-900 tracking-tight">MARC ON</span>
          </div>
          <nav className="flex space-x-10 font-bold text-gray-500 text-sm">
            <button
              type="button"
              onClick={() => setCurrentView('home')}
              className={`pb-5 pt-5 transition-all border-b-2 ${currentView === 'home' ? 'text-blue-600 border-blue-600' : 'border-transparent hover:text-blue-600'}`}
            >
              홈
            </button>
            <button
              type="button"
              onClick={() => setCurrentView('results')}
              className={`pb-5 pt-5 transition-all border-b-2 ${currentView === 'results' ? 'text-blue-600 border-blue-600' : 'border-transparent hover:text-blue-600'}`}
            >
              결과
            </button>
            <button
              type="button"
              onClick={() => setCurrentView('history')}
              className={`pb-5 pt-5 transition-all border-b-2 ${currentView === 'history' ? 'text-blue-600 border-blue-600' : 'border-transparent hover:text-blue-600'}`}
            >
              이력
            </button>
            <button
              type="button"
              onClick={() => setCurrentView('settings')}
              className={`pb-5 pt-5 transition-all border-b-2 ${currentView === 'settings' ? 'text-blue-600 border-blue-600' : 'border-transparent hover:text-blue-600'}`}
            >
              설정
            </button>
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        {currentView === 'home' && (
          <div className="space-y-12">
            <section className="bg-white border border-gray-200 rounded-2xl p-10 shadow-sm">
              <div className="max-w-2xl">
                <h1 className="text-3xl font-extrabold text-gray-900 mb-3 tracking-tight">
                  KORMARC 레코드 생성
                </h1>
                <p className="text-gray-500 text-base mb-8 font-medium">
                  ISBN을 입력하면 외부 서지 API를 조회하고 LLM으로 MARC 초안을 생성합니다.
                </p>
                <button
                  type="button"
                  onClick={() => handleInputMethodJump('single')}
                  className="bg-black hover:bg-gray-800 text-white font-bold text-sm px-8 py-3 rounded-xl transition-all tracking-wide"
                >
                  MARC 생성하기
                </button>
              </div>
            </section>

            <section>
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-extrabold text-gray-900 tracking-tight">최근 생성 결과</h2>
                <button type="button" onClick={() => setCurrentView('results')} className="text-xs text-blue-600 font-bold hover:underline">
                  전체 보기
                </button>
              </div>

              {recentHistory.length === 0 ? (
                <div className="bg-white border border-gray-200 rounded-xl p-6 text-sm font-semibold text-gray-500">
                  아직 생성된 MARC 결과가 없습니다.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  {recentHistory.map((item) => (
                    <button
                      type="button"
                      key={item.id}
                      onClick={() => {
                        setSelectedBook(item);
                        setCurrentView('inspect');
                      }}
                      className="text-left bg-white border border-gray-200 rounded-xl p-5 shadow-sm hover:border-gray-400 cursor-pointer transition flex flex-col justify-between min-h-[140px]"
                    >
                      <div>
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-xs font-medium text-gray-400">{item.createdAt}</span>
                          <StatusBadge status={item.status} />
                        </div>
                        <h3 className="font-extrabold text-base text-gray-800 line-clamp-2">{item.title}</h3>
                      </div>
                      <div className="text-xs text-gray-400 font-medium font-mono">{item.isbn}</div>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <button type="button" onClick={() => handleInputMethodJump('single')} className="text-left bg-white p-6 border border-gray-200 rounded-xl cursor-pointer hover:border-gray-400 transition">
                <h4 className="font-extrabold text-sm text-gray-900 mb-1">단일 ISBN 입력</h4>
                <p className="text-gray-400 text-xs leading-relaxed font-medium">한 권의 도서를 조회하고 MARC 초안을 생성합니다.</p>
              </button>
              <button type="button" onClick={() => handleInputMethodJump('multiple')} className="text-left bg-white p-6 border border-gray-200 rounded-xl cursor-pointer hover:border-gray-400 transition">
                <h4 className="font-extrabold text-sm text-gray-900 mb-1">복수 ISBN 입력</h4>
                <p className="text-gray-400 text-xs leading-relaxed font-medium">추후 배치 생성 흐름을 연결할 영역입니다.</p>
              </button>
              <button type="button" onClick={() => handleInputMethodJump('manual')} className="text-left bg-white p-6 border border-gray-200 rounded-xl cursor-pointer hover:border-gray-400 transition">
                <h4 className="font-extrabold text-sm text-gray-900 mb-1">직접 입력</h4>
                <p className="text-gray-400 text-xs leading-relaxed font-medium">ISBN이 없는 도서의 수기 입력 생성 흐름을 준비합니다.</p>
              </button>
            </section>
          </div>
        )}

        {currentView === 'input' && (
          <MARCInput
            initialTab={activeInputTab}
            onGenerated={handleGenerated}
            onCancel={() => setCurrentView('home')}
          />
        )}

        {currentView === 'results' && (
          <MARCResultList
            results={generatedResults}
            onSelectDetail={(book) => {
              setSelectedBook(book);
              setCurrentView('inspect');
            }}
            onCreate={() => handleInputMethodJump('single')}
          />
        )}

        {currentView === 'inspect' && (
          <MARCInspection
            selectedBook={selectedBook}
            onBackToList={() => setCurrentView('results')}
          />
        )}

        {currentView === 'history' && (
          <MARCHistory
            onSelectTask={() => setCurrentView('results')}
          />
        )}

        {currentView === 'settings' && (
          <MARCSettings />
        )}
      </main>
    </div>
  );
}
