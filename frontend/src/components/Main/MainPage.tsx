// src/components/Main/MainPage.tsx
import Header from '../Header/Header';

export default function MainPage() {
  return (
    <div className="min-h-screen bg-gray-100">
      <Header />
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          <div className="bg-white rounded-lg shadow p-6">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">メイン画面</h1>
            <p className="text-gray-600">ログインに成功しました！</p>
          </div>
        </div>
      </main>
    </div>
  );
}