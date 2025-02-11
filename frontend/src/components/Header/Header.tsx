import { useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

const Header = () => {
  const { currentUser, setCurrentUser } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      // ユーザー状態をクリア
      setCurrentUser(null);
      // ログインページにリダイレクト
      navigate("/");
    } catch (error) {
      console.error("ログアウトエラー:", error);
    }
  };

  return (
    <header className="bg-dark-primary p-2 mb-2">
      <div className="container mx-auto flex justify-between items-center">
        <button
          onClick={() => navigate("/app/main")}
          className="text-white text-xl font-bold hover:text-gray-300"
        >
          Home
        </button>
        <div className="flex items-center gap-4">
          <span className="text-white">{currentUser?.email}</span>
          <button
            onClick={handleLogout}
            className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
          >
            ログアウト
          </button>
        </div>
      </div>
    </header>
  );
};

export default Header;