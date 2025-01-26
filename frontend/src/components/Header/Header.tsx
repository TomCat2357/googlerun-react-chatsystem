import LogoutButton from '../Auth/LogoutButton';

export default function Header() {
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
                <LogoutButton />
            </div>
        </header>
    );
}