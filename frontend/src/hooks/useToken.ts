// src/hooks/useToken.ts
import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";

export function useToken(): string {
  const { currentUser } = useAuth();
  const [token, setToken] = useState("");

  useEffect(() => {
    if (currentUser) {
      currentUser
        .getIdToken()
        .then((t) => setToken(t))
        .catch((err) => console.error("トークン取得エラー:", err));
    }
  }, [currentUser]);

  return token;
}
