import { getAuth } from 'firebase/auth';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import * as Config from '../../config';

export default function LogoutButton() {
  const navigate = useNavigate();

  const handleLogout = async () => {
    const auth = getAuth();
    try {
      console.log("Firebaseからサインアウトを試みています");
      await auth.signOut();

      // browserSessionPersistence を利用している場合、IndexedDB は使用されないが、
      // 念のため IndexedDB の "firebaseLocalStorageDb" を削除
      const dbName = "firebaseLocalStorageDb";
      const deleteRequest = indexedDB.deleteDatabase(dbName);
      deleteRequest.onsuccess = function () {
        console.log(`IndexedDB ${dbName} の削除に成功しました`);
      };
      deleteRequest.onerror = function (event) {
        console.error(`IndexedDB ${dbName} の削除に失敗しました`, event);
      };

      // サーバー側のログアウトAPIを呼び出す
      await axios.post(`${Config.API_BASE_URL}/backend/logout`, null, {
        withCredentials: true
      });
      navigate('/');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  return (
    <button
      onClick={handleLogout}
      style={{
        padding: '0.5rem 1rem',
        backgroundColor: '#dc3545',
        color: 'white',
        border: 'none',
        borderRadius: '4px',
        cursor: 'pointer'
      }}
    >
      ログアウト
    </button>
  );
}
