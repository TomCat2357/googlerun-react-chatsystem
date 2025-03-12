import { useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import LogoutButton from "../Auth/LogoutButton"; // LogoutButtonをインポート
import * as Config from "../../config";

const Header = () => {
  const { currentUser } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="bg-dark-primary p-2 mb-2">
      <div className="container mx-auto flex justify-between items-center">
        <button
          onClick={() => navigate(Config.getClientPath("/app/main"))}
          className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
        >
          ホーム
        </button>
        <div className="flex items-center gap-4">
          <span className="text-white">{currentUser?.email}</span>
          <LogoutButton /> {/* LogoutButtonコンポーネントを使用 */}
        </div>
      </div>
    </header>
  );
};

export default Header; // この行が欠けていました