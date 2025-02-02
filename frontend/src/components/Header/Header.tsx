import LogoutButton from '../Auth/LogoutButton';

export default function Header() {
    return (
        <header className="fixed top-0 left-0 w-full h-[48px] bg-gray-800 
                          flex justify-between items-center px-4 
                          shadow-lg shadow-gray-900/50 z-50">
            <div className="text-lg font-bold text-gray-100">
                メインUI
            </div>
            <div className="flex items-center">
                <LogoutButton />
            </div>
        </header>
    );
}