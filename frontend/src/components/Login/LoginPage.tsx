// src/components/Login/LoginPage.tsx
import LoginButton from '../Auth/LoginButton';

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0A0A0A] flex flex-col justify-center items-center">
      <div className="bg-[#141414] p-8 rounded-xl shadow-2xl border border-zinc-800">
        <h1 className="text-3xl font-bold text-zinc-100 mb-8 text-center">
          チャットシステム
        </h1>
        <LoginButton />
      </div>
    </div>
  );
}