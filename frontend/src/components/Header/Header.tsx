import { getAuth } from 'firebase/auth';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';  // この行を追加
export default function Header() {
    const navigate = useNavigate();

    const handleLogout = async () => {
        const auth = getAuth();
        try {
            await auth.signOut();
            await axios.post('http://localhost:8080/app/logout', null, {
                withCredentials: true
            });
            navigate('/');
        } catch (error) {
            console.error('Logout error:', error);
        }
    };

    return (
        <header style={{
            width: '100%',
            position: 'fixed',
            top: 0,
            left: 0,
            padding: '1rem',
            backgroundColor: '#f8f9fa',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            zIndex: 1000
        }}>
            <div style={{
                fontSize: '1.2rem',
                fontWeight: 'bold',
                marginLeft: '2rem'
            }}>
                メインUI
            </div>
            <div style={{
                display: 'flex',
                alignItems: 'center',
                marginRight: '2rem'
            }}>
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
            </div>
        </header>
    );
}