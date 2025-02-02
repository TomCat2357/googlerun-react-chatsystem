import { getAuth } from 'firebase/auth';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

export default function LogoutButton() {
    const navigate = useNavigate();

    const handleLogout = async () => {
        const auth = getAuth();
        try {
            await auth.signOut();
            await axios.post(`${import.meta.env.VITE_API_BASE_URL}/backend/logout`, null, {
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
