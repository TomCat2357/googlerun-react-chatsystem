// src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import LoginPage from './components/Login/LoginPage';
import MainPage from './components/Main/MainPage';
import Header from './components/Header/Header';

function App() {
  return (
    <BrowserRouter>
      <div>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/main" element={
            <>
              <Header />
              <MainPage />
            </>
          } />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;